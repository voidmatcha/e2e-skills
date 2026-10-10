#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare the pinned scanner arm with historical real-fix controls."""

import argparse
import collections
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "benchmarks/real-fix-scanner-inclusive-v1/protocol.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finding_key(call, finding):
    return (call["case"], call["side"], finding["file"], finding["line"], finding["pattern_id"])


def extra_keys(call):
    scored = call["score"]
    excluded = collections.Counter(
        finding_key(call, finding)
        for finding in scored.get("target_findings", []) + scored.get("mapped_after_alarms", [])
    )
    extras = []
    for finding in call["answer"]["findings"]:
        key = finding_key(call, finding)
        if excluded[key]:
            excluded[key] -= 1
        else:
            extras.append(key)
    if sum(excluded.values()) or len(extras) != scored["other_findings_unadjudicated"]:
        raise ValueError("extra finding count or exclusion drift")
    return extras


def selected_calls(report, host, arm, cases):
    selected = {(call["case"], call["side"]): call for call in report["calls"]
                if call["case"] in cases and call["arm"] == arm
                and ("host" not in call or call["host"] == host)}
    expected = {(case, side) for case in cases for side in ("before", "after")}
    if set(selected) != expected or not all(call["complete"] for call in selected.values()):
        raise ValueError(f"incomplete or duplicate {host}/{arm} calls")
    return selected


def usage_sum(calls, field):
    values = [call["usage"].get(field) for call in calls.values()]
    return None if any(value is None for value in values) else sum(values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", required=True, type=Path)
    for host in ("sol", "astra", "claude"):
        parser.add_argument(f"--{host}", required=True, type=Path)
    parser.add_argument("--ledgers", nargs="+", required=True, type=Path)
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="describe only fully completed host cohorts; never impute missing calls")
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text())
    live = json.loads(args.live.read_text())
    if live["protocol_sha256"] != digest(PROTOCOL):
        raise ValueError("protocol drift")
    if live["status"] != "COMPLETE" and not (args.allow_incomplete and live["status"] == "INCOMPLETE"):
        raise ValueError("live report incomplete")
    if len(live["scanner"]) != 10 or (live["status"] == "COMPLETE" and len(live["calls"]) != 30):
        raise ValueError("scanner or live schedule incomplete")
    if not all(call["complete"] for call in live["calls"]):
        raise ValueError("unscoreable completed call")
    for packet, expected in protocol["scanner"]["normalized_packet_sha256"].items():
        if live["scanner"][packet]["normalized_sha256"] != expected:
            raise ValueError(f"scanner packet drift: {packet}")

    baselines = {}
    for host in protocol["hosts"]:
        name = host["key"]
        path = getattr(args, name)
        if digest(path) != host["baseline_sha256"]:
            raise ValueError(f"baseline digest drift: {name}")
        baselines[name] = json.loads(path.read_text())

    ledgers = {}
    for path in args.ledgers:
        ledger = json.loads(path.read_text())
        if ledger["status"] != "COMPLETE":
            raise ValueError(f"incomplete ledger: {path}")
        for row in ledger["rows"]:
            key = (row["case"], row["side"], row["file"], row["line"], row["pattern_id"])
            if key in ledgers:
                raise ValueError(f"duplicate ledger key: {key}")
            ledgers[key] = row["verdict"]

    output = {"status": live["status"], "completed_calls": len(live["calls"]),
              "evidence_class": protocol["evidence_class"],
              "protocol_sha256": digest(PROTOCOL), "live_report_sha256": digest(args.live),
              "baseline_report_sha256": {h["key"]: h["baseline_sha256"] for h in protocol["hosts"]},
              "ledger_sha256": {path.name: digest(path) for path in args.ledgers},
              "scanner_elapsed_seconds": round(sum(p["elapsed_ms"] for p in live["scanner"].values()) / 1000, 3),
              "scanner_packet_bytes": sum(p["normalized_bytes"] for p in live["scanner"].values()),
              "models": {}}
    new_keys = set()
    for host in protocol["hosts"]:
        name = host["key"]
        observed = [call for call in live["calls"] if call["host"] == name]
        if len(observed) != 10:
            if live["status"] == "COMPLETE":
                raise ValueError(f"completed report lacks host: {name}")
            output.setdefault("incomplete_hosts", {})[name] = len(observed)
            continue
        current = selected_calls(live, name, "full+scanner", protocol["cases"])
        controls = {arm: selected_calls(baselines[name], name, arm, protocol["cases"])
                    for arm in ("full", "catalog-only")}
        hit_cases = [case for case in protocol["cases"] if current[(case, "before")]["score"]["target_detected"]]
        paired = {}
        for arm, control in controls.items():
            paired[arm] = {
                "gained": [case for case in protocol["cases"]
                           if current[(case, "before")]["score"]["target_detected"]
                           and not control[(case, "before")]["score"]["target_detected"]],
                "lost": [case for case in protocol["cases"]
                         if control[(case, "before")]["score"]["target_detected"]
                         and not current[(case, "before")]["score"]["target_detected"]],
                "control_hits": sum(bool(control[(case, "before")]["score"]["target_detected"])
                                    for case in protocol["cases"]),
            }
        extra_verdicts = collections.Counter()
        for call in current.values():
            for key in extra_keys(call):
                if key in ledgers:
                    extra_verdicts[ledgers[key]] += 1
                else:
                    extra_verdicts["UNADJUDICATED_NEW_KEY"] += 1
                    new_keys.add(key)
        output["models"][name] = {
            "target_hits": len(hit_cases), "hit_cases": hit_cases, "paired": paired,
            "mapped_after_alarms": sum(len(current[(case, "after")]["score"].get("mapped_after_alarms", []))
                                       for case in protocol["cases"]),
            "other_predictions": dict(extra_verdicts),
            "usage": {field: usage_sum(current, field) for field in
                      ("input_tokens", "cached_input_tokens", "cache_write_tokens",
                       "output_tokens", "reasoning_output_tokens")},
            "summed_call_seconds": round(sum(c["elapsed_ms"] for c in current.values()) / 1000, 3),
        }
    output["new_unique_keys"] = [list(key) for key in sorted(new_keys)]
    output["new_unique_key_count"] = len(new_keys)
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

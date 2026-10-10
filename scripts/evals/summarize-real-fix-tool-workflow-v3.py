#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarize the frozen v3 tool-workflow report and source adjudications."""

import argparse
import collections
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/real-fix-tool-workflow-v3"


def read_json(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    protocol_path = BENCH / "protocol.json"
    protocol = read_json(protocol_path)
    report = read_json(args.report)
    if report["status"] != "COMPLETE" or report["protocol_sha256"] != digest(protocol_path):
        raise SystemExit("report is incomplete or does not match frozen protocol")
    if len(report["calls"]) != len(protocol["schedule"]):
        raise SystemExit("call count does not match schedule")

    ledgers = {}
    ledger_digests = {}
    for case in protocol["targets"]:
        path = BENCH / f"adjudication-{case}.json"
        ledger = read_json(path)
        if ledger["status"] != "COMPLETE":
            raise SystemExit(f"incomplete adjudication: {case}")
        rows = {
            (row["side"], row["file"], row["line"], row["pattern_id"]): row["verdict"]
            for row in ledger["rows"]
        }
        if len(rows) != len(ledger["rows"]):
            raise SystemExit(f"duplicate adjudication key: {case}")
        ledgers[case] = rows
        ledger_digests[case] = digest(path)

    arms = {}
    seen_by_case = collections.defaultdict(set)
    for arm in ("workflow", "legend-only"):
        arms[arm] = {
            "calls": 0,
            "target_hits": [],
            "mapped_after_alarms": [],
            "scanner_commands": 0,
            "scanner_summaries": 0,
            "shell_commands": 0,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "model_call_seconds": 0.0,
            "off_target_predictions_by_verdict": collections.Counter(),
            "unique_off_target_keys": set(),
        }

    for actual, expected in zip(report["calls"], protocol["schedule"], strict=True):
        if any(actual[k] != expected[k] for k in ("case", "side", "arm")):
            raise SystemExit("call order differs from frozen schedule")
        case, side, arm = actual["case"], actual["side"], actual["arm"]
        out = arms[arm]
        out["calls"] += 1
        out["scanner_commands"] += actual["scanner_command_count"]
        out["scanner_summaries"] += actual["scanner_summary_count"]
        out["shell_commands"] += actual["command_count"]
        out["model_call_seconds"] += actual["elapsed_seconds"]
        for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
            out[key] += actual["usage"][key]
        target = protocol["targets"][case]
        spec_files = [
            name for name in protocol["source_sha256"][f"{case}:{side}"]["files"]
            if name.endswith((".spec.ts", ".test.ts", ".cy.js"))
        ]
        if len(spec_files) != 1:
            raise SystemExit(f"expected exactly one E2E spec: {case} {side}")
        spec_file = spec_files[0]
        for finding in actual["answer"]["findings"]:
            key = (side, finding["file"], finding["line"], finding["pattern_id"])
            target_hit = (
                side == "before"
                and finding["file"] == spec_file
                and finding["pattern_id"] == target["pattern"]
                and finding["line"] in target["before_lines"]
            )
            if target_hit:
                out["target_hits"].append(case)
                continue
            if (
                side == "after"
                and finding["file"] == spec_file
                and finding["pattern_id"] == target["pattern"]
                and target["after_range"][0] <= finding["line"] <= target["after_range"][1]
            ):
                out["mapped_after_alarms"].append(case)
            if key not in ledgers[case]:
                raise SystemExit(f"unadjudicated prediction: {case} {arm} {key}")
            out["off_target_predictions_by_verdict"][ledgers[case][key]] += 1
            out["unique_off_target_keys"].add((case, *key))
            seen_by_case[case].add(key)
        if side == "before" and actual["score"]["target_detected"] != (case in out["target_hits"]):
            raise SystemExit(f"target score drift: {case} {arm}")
        if side == "after" and bool(actual["score"]["mapped_after_alarms"]) != (case in out["mapped_after_alarms"]):
            raise SystemExit(f"AFTER alarm score drift: {case} {arm}")

    for case, keys in seen_by_case.items():
        if keys != set(ledgers[case]):
            raise SystemExit(f"adjudication coverage differs from predictions: {case}")
    for arm, out in arms.items():
        out["target_hits"] = sorted(set(out["target_hits"]))
        out["mapped_after_alarms"] = sorted(set(out["mapped_after_alarms"]))
        out["off_target_predictions_by_verdict"] = dict(sorted(out["off_target_predictions_by_verdict"].items()))
        out["unique_off_target_keys"] = len(out["unique_off_target_keys"])
        out["model_call_seconds"] = round(out["model_call_seconds"], 3)
        if out["calls"] != 6 or (arm == "workflow" and out["scanner_summaries"] < 6):
            raise SystemExit(f"missing calls or scanner proof: {arm}")

    print(json.dumps({
        "status": "COMPLETE",
        "protocol_sha256": digest(protocol_path),
        "raw_report_sha256": digest(args.report),
        "adjudication_sha256": ledger_digests,
        "unique_off_target_keys_all_arms": sum(map(len, seen_by_case.values())),
        "arms": arms,
    }, indent=2))


if __name__ == "__main__":
    main()

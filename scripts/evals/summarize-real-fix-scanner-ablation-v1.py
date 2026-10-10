#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check and summarize the frozen same-skill scanner ablation."""

import argparse
import collections
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/real-fix-scanner-ablation-v1"
CASE_INDEX = {"growi": ("v9", 1), "chronograf": ("v10", 0), "opensearch": ("v9", 2)}
EXPECTED_SEVERITY = {"growi": "P1", "chronograf": "P1", "opensearch": "P0"}


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
        raise SystemExit("incomplete report or protocol mismatch")
    for key in ("runner_sha256", "skill_tree_sha256", "source_sha256", "schedule"):
        if report[key] != protocol[key]:
            raise SystemExit(f"report identity drift: {key}")
    if len(report["calls"]) != len(protocol["schedule"]):
        raise SystemExit("call count differs from frozen schedule")

    labels, ledgers, ledger_digests = {}, {}, {}
    for case, (version, index) in CASE_INDEX.items():
        source_case = read_json(ROOT / f"benchmarks/real-fix-acquisition-{version}/cases.json")[index]
        if source_case["pattern"] != protocol["targets"][case]["pattern"]:
            raise SystemExit(f"source target drift: {case}")
        if source_case["severity"] != EXPECTED_SEVERITY[case]:
            raise SystemExit(f"source severity label drift: {case}")
        for side, revision in (("before", "parent"), ("after", "fix")):
            if source_case[revision] != protocol["source_sha256"][f"{case}:{side}"]["revision"]:
                raise SystemExit(f"source revision drift: {case} {side}")
        labels[case] = source_case["severity"]
        path = BENCH / f"adjudication-{case}.json"
        ledger = read_json(path)
        if ledger["status"] != "COMPLETE":
            raise SystemExit(f"incomplete adjudication: {case}")
        if ledger.get("report_sha256") != digest(args.report):
            raise SystemExit(f"ledger report identity drift: {case}")
        if ledger.get("protocol_sha256") != digest(protocol_path):
            raise SystemExit(f"ledger protocol identity drift: {case}")
        for side in ("before", "after"):
            expected_source = protocol["source_sha256"][f"{case}:{side}"]
            spec_files = [name for name in expected_source["files"]
                          if name.endswith((".spec.ts", ".test.ts", ".cy.js"))]
            if len(spec_files) != 1:
                raise SystemExit(f"expected one source spec: {case} {side}")
            spec_file = spec_files[0]
            identity = ledger["source_sha256"]
            if case == "chronograf":
                actual_digest = identity[side]
            else:
                actual_digest = identity[f"{case}:{side}"]["files"][spec_file]
                if identity[f"{case}:{side}"]["revision"] != expected_source["revision"]:
                    raise SystemExit(f"ledger revision drift: {case} {side}")
            if actual_digest != expected_source["files"][spec_file]:
                raise SystemExit(f"ledger source digest drift: {case} {side}")
        rows = {
            (row["side"], row["file"], row["line"], row["pattern_id"]): row["verdict"]
            for row in ledger["rows"]
        }
        if len(rows) != len(ledger["rows"]):
            raise SystemExit(f"duplicate ledger key: {case}")
        ledgers[case] = rows
        ledger_digests[case] = digest(path)

    arms = {}
    for arm in ("scanner", "no-scanner"):
        arms[arm] = {
            "calls": 0,
            "exact_target_hits": [],
            "correct_severity_target_hits_exploratory": [],
            "near_target_wrong_anchor_exploratory": [],
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
    union_keys = collections.defaultdict(set)

    for cell, expected in zip(report["calls"], protocol["schedule"], strict=True):
        if any(cell[key] != expected[key] for key in ("case", "side", "arm")):
            raise SystemExit("call order differs from frozen schedule")
        case, side, arm = cell["case"], cell["side"], cell["arm"]
        out = arms[arm]
        out["calls"] += 1
        for source, target in (("scanner_command_count", "scanner_commands"),
                               ("scanner_summary_count", "scanner_summaries"),
                               ("command_count", "shell_commands")):
            out[target] += cell[source]
        for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
            out[key] += cell["usage"][key]
        out["model_call_seconds"] += cell["elapsed_seconds"]
        if arm == "scanner" and (cell["scanner_command_count"] < 1 or
                                  cell["scanner_command_count"] != cell["scanner_summary_count"]):
            raise SystemExit(f"scanner missing or incomplete: {case} {side}")
        if arm == "no-scanner" and cell["scanner_command_count"]:
            raise SystemExit(f"scanner used in ablated arm: {case} {side}")

        target = protocol["targets"][case]
        spec_files = [
            name for name in protocol["source_sha256"][f"{case}:{side}"]["files"]
            if name.endswith((".spec.ts", ".test.ts", ".cy.js"))
        ]
        if len(spec_files) != 1:
            raise SystemExit(f"expected one spec: {case} {side}")
        spec = spec_files[0]
        for finding in cell["answer"]["findings"]:
            key = (side, finding["file"], finding["line"], finding["pattern_id"])
            same_pattern = finding["file"] == spec and finding["pattern_id"] == target["pattern"]
            before_hit = side == "before" and same_pattern and finding["line"] in target["before_lines"]
            after_alarm = (side == "after" and same_pattern and
                           target["after_range"][0] <= finding["line"] <= target["after_range"][1])
            if before_hit:
                out["exact_target_hits"].append(case)
                if finding["severity"] == labels[case]:
                    out["correct_severity_target_hits_exploratory"].append(case)
                continue
            if after_alarm:
                out["mapped_after_alarms"].append(case)
            if side == "before" and same_pattern and any(
                0 < abs(finding["line"] - line) <= 2 for line in target["before_lines"]
            ):
                out["near_target_wrong_anchor_exploratory"].append(case)
            if key not in ledgers[case]:
                raise SystemExit(f"unadjudicated prediction: {case} {arm} {key}")
            out["off_target_predictions_by_verdict"][ledgers[case][key]] += 1
            out["unique_off_target_keys"].add((case, *key))
            union_keys[case].add(key)
        if side == "before" and cell["score"]["target_detected"] != (case in out["exact_target_hits"]):
            raise SystemExit(f"target score drift: {case} {arm}")
        if side == "after" and bool(cell["score"]["mapped_after_alarms"]) != (case in out["mapped_after_alarms"]):
            raise SystemExit(f"AFTER score drift: {case} {arm}")

    for case, ledger in ledgers.items():
        if union_keys[case] != set(ledger):
            raise SystemExit(f"ledger coverage drift: {case}")
    for out in arms.values():
        for key in ("exact_target_hits", "correct_severity_target_hits_exploratory",
                    "near_target_wrong_anchor_exploratory", "mapped_after_alarms"):
            out[key] = sorted(set(out[key]))
        out["off_target_predictions_by_verdict"] = dict(sorted(out["off_target_predictions_by_verdict"].items()))
        out["unique_off_target_keys"] = len(out["unique_off_target_keys"])
        out["model_call_seconds"] = round(out["model_call_seconds"], 3)
        if out["calls"] != 6:
            raise SystemExit("missing arm call")
    print(json.dumps({
        "status": "COMPLETE",
        "protocol_sha256": digest(protocol_path),
        "raw_report_sha256": digest(args.report),
        "adjudication_sha256": ledger_digests,
        "source_label_severity": labels,
        "unique_off_target_keys_all_arms": sum(map(len, union_keys.values())),
        "arms": arms,
    }, indent=2))


if __name__ == "__main__":
    main()

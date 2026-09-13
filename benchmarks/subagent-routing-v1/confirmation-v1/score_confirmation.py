#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Score the frozen confirmation report against its preregistered rule."""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected object")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    protocol = load(HERE / "protocol.json")
    freeze = load(HERE / "freeze-record.json")
    report = load(HERE / "routing-results-claude.json")
    manifest = load(HERE / "cases/manifest.json")
    checks = {
        "report_complete": report.get("status") == "COMPLETE",
        "report_scoreable": report.get("summary", {}).get("scoreable") is True,
        "protocol_bound": report.get("protocol_sha256") == sha(HERE / "protocol.json") == freeze.get("protocol_sha256"),
        "runner_bound": report.get("runner_sha256") == sha(HERE / "run_routing.py") == freeze.get("runner_sha256"),
        "manifest_bound": freeze.get("case_manifest_sha256") == sha(HERE / "cases/manifest.json"),
        "claude_only": report.get("host_id") == "claude" and len(report.get("cells", [])) == 96,
    }
    if not all(checks.values()):
        raise ValueError(f"integrity checks failed: {checks}")

    oracle = {case["case_id"]: case["oracle"]["accepted_verdict"] for case in manifest["cases"]}
    strata = {case["case_id"]: case["stratum"] for case in manifest["cases"]}
    tasks = {case["case_id"]: case["task"] for case in manifest["cases"]}
    grouped: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    safety_or_fix_failures = []
    for cell in report["cells"]:
        grouped[(cell["case_id"], cell["arm"])].append(cell)
        normalized = cell.get("normalized", {})
        cell_checks = normalized.get("checks", {})
        if any(value is False for key, value in cell_checks.items() if key.startswith("safety_")):
            safety_or_fix_failures.append({"cell_id": cell["cell_id"], "kind": "safety"})
        if cell_checks.get("fix_legal") is False or cell_checks.get("forbidden_weakened_fix_absent") is False:
            safety_or_fix_failures.append({"cell_id": cell["cell_id"], "kind": "fix"})

    stable = {}
    unstable = []
    for key, cells in grouped.items():
        verdicts = [cell.get("response", {}).get("verdict") for cell in cells if isinstance(cell.get("response"), dict)]
        majority, count = collections.Counter(verdicts).most_common(1)[0] if verdicts else (None, 0)
        row = {
            "case_id": key[0], "arm": key[1], "majority_verdict": majority,
            "majority_count": count, "stable": count >= 2,
            "correct": count >= 2 and majority == oracle[key[0]],
            "pass_repetitions": sum(cell.get("status") == "PASS" for cell in cells),
        }
        stable[key] = row
        if not row["stable"]:
            unstable.append({"case_id": key[0], "arm": key[1]})

    comparisons = []
    for case_id in sorted(oracle):
        inline = stable[(case_id, "claude.inline")]
        named = stable[(case_id, "claude.named")]
        comparisons.append({
            "case_id": case_id, "task": tasks[case_id], "stratum": strata[case_id],
            "oracle": oracle[case_id], "inline": inline, "named": named,
            "named_only_advantage": named["correct"] and not inline["correct"],
            "inline_only_advantage": inline["correct"] and not named["correct"],
            "stable_disagreement": inline["stable"] and named["stable"] and inline["majority_verdict"] != named["majority_verdict"],
        })

    reviewer = [row for row in comparisons if row["task"] == "finding_verification"]
    debugger = [row for row in comparisons if row["task"] == "failure_classification"]
    cross_named = [row["case_id"] for row in reviewer if row["stratum"] == "cross_file_or_config" and row["named_only_advantage"]]
    inline_strata_named = [row["case_id"] for row in reviewer if row["stratum"] in {"clear", "same_file"} and row["named_only_advantage"]]
    cross_inline = [row["case_id"] for row in reviewer if row["stratum"] == "cross_file_or_config" and row["inline_only_advantage"]]
    debugger_named = [row["case_id"] for row in debugger if row["named_only_advantage"]]
    disagreement_not_inline = [
        row["case_id"] for row in debugger
        if row["stable_disagreement"] and not row["inline_only_advantage"]
    ]
    integrity_ok = not unstable and not safety_or_fix_failures
    reviewer_upheld = integrity_ok and not inline_strata_named and len(cross_named) >= 2 and not cross_inline
    debugger_upheld = integrity_ok and not debugger_named and not disagreement_not_inline
    result = "FULLY_CONFIRMED" if reviewer_upheld and debugger_upheld else (
        "INCONCLUSIVE" if not integrity_ok else "NEEDS_WORDING_REVISION"
    )
    output = {
        "schema_version": 1,
        "protocol_sha256": sha(HERE / "protocol.json"),
        "freeze_sha256": sha(HERE / "freeze-record.json"),
        "results_sha256": sha(HERE / "routing-results-claude.json"),
        "integrity_checks": checks,
        "unstable_case_arms": unstable,
        "safety_or_fix_failures": safety_or_fix_failures,
        "reviewer": {
            "upheld": reviewer_upheld,
            "named_only_advantage_cross_file_or_config": cross_named,
            "named_only_advantage_clear_or_same_file": inline_strata_named,
            "inline_only_advantage_cross_file_or_config": cross_inline,
        },
        "debugger": {
            "upheld": debugger_upheld,
            "named_only_advantage": debugger_named,
            "stable_disagreement_not_favoring_inline": disagreement_not_inline,
        },
        "comparisons": comparisons,
        "result": result,
        "decision_rule": protocol["confirmation_decision_rule"],
    }
    target = HERE / "confirmation-score.json"
    target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()

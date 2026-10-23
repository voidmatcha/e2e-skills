#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read one pinned holdout cell for Promptfoo. Never invoke a model or grader."""

import hashlib
import json
from pathlib import Path
import sys


def project(request):
    if set(request) != {"report", "sha256", "case"}:
        raise ValueError("expected report, sha256 and case")
    path = Path(request["report"])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("report must be an absolute regular file")
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != request["sha256"]:
        raise ValueError("report digest mismatch")
    report = json.loads(data)
    if report.get("status") not in {"PASS", "FAIL", "INCONCLUSIVE"}:
        raise ValueError("unknown source verdict")
    runs = report.get("runs", [])
    if not isinstance(runs, list) or len(runs) != 1:
        raise ValueError("canary requires exactly one recorded cell")
    run = runs[0]
    if run.get("case") != request["case"]:
        raise ValueError("case identity mismatch")
    # Keep the original cell intact, including errors, findings, scoring and usage.
    return {
        "mode": "recorded-report", "model_calls_by_provider": 0,
        "cost_scope": "Promptfoo replay only; original model usage/cost may be unavailable",
        "report": str(path), "report_sha256": actual,
        "source_status": report["status"],
        "source_status_reasons": report.get("status_reasons"),
        "source_complete": report.get("complete"),
        "source_execution_complete": report.get("execution_complete"),
        "release_eligible": report.get("release_eligible", False),
        "runner": report.get("runner"), "model": report.get("model"),
        "prompt_profile": report.get("prompt_profile"),
        "skill_sha256": report.get("skill_sha256"),
        "corpus_sha256": report.get("corpus_sha256"),
        "model_tool_surface": report.get("model_tool_surface"),
        "source_usage_summary": report.get("usage_summary"),
        "cell_count": 1, "cell": run,
    }


if __name__ == "__main__":
    try:
        # exec providers pass prompt, provider options and test context as argv.
        print(json.dumps(project(json.loads(sys.argv[1]))))
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        print(f"report adapter error: {error}", file=sys.stderr)
        sys.exit(2)

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Supplemental consistency admission; preserves the frozen v1 verifier bytes."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "check-docker-matrix"))
import verify_notepad_split as legacy


def require(condition, detail):
    if not condition:
        raise RuntimeError(f"native outcome consistency: {detail}")


def validate_report(report: dict, expected_failure: bool) -> None:
    """Reject contradictory Playwright summaries even when attempt data agrees."""
    require(type(expected_failure) is bool, "failure expectation must be boolean")
    require(not report.get("errors"), "global errors")
    stats = report["stats"]
    expected = {"expected": int(not expected_failure), "unexpected": int(expected_failure),
                "skipped": 0, "flaky": 0}
    require(all(type(stats.get(key)) is int and stats[key] == value
                for key, value in expected.items()), "stats")
    require(report["config"]["workers"] == 1
            and type(report["config"]["workers"]) is int, "workers")
    projects = report["config"]["projects"]
    require(len(projects) == 1 and type(projects[0]["retries"]) is int
            and projects[0]["retries"] == 0, "retry configuration")
    suites = report["suites"]
    require(len(suites) == 1 and not suites[0].get("suites"), "suite scope")
    specs = suites[0]["specs"]
    require(len(specs) == 1, "spec count")
    spec = specs[0]
    require(type(spec.get("ok")) is bool and spec["ok"] == (not expected_failure), "spec.ok")
    tests = spec["tests"]
    require(len(tests) == 1, "test count")
    test = tests[0]
    require(test["expectedStatus"] == "passed"
            and test["status"] == ("unexpected" if expected_failure else "expected"), "test outcome")
    attempts = test["results"]
    require(len(attempts) == 1, "attempt count")
    attempt = attempts[0]
    require(attempt["status"] == ("failed" if expected_failure else "passed")
            and type(attempt["retry"]) is int and attempt["retry"] == 0, "attempt outcome")
    errors = attempt.get("errors", [])
    if expected_failure:
        primary = attempt.get("error", {})
        require(len(errors) == 1 and errors[0].get("location") == primary.get("location")
                and bool(primary.get("message"))
                and errors[0].get("message", "").startswith(primary["message"]), "failure errors")
    else:
        require(not errors and not attempt.get("error"), "passing attempt carries error")


def validate_cell(root: Path, name: str) -> dict:
    try:
        report = json.loads((root / name / "test-out/report.json").read_text())
        validate_report(report, name == "strong-fault")
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise RuntimeError(f"native outcome consistency: malformed report: {error}") from error
    return legacy.validate_cell(root, name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--cell", required=True)
    args = parser.parse_args()
    print(json.dumps(validate_cell(args.root.resolve(), args.cell)))

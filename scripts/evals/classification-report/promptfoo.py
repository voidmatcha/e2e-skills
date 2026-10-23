#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Display a frozen classification JSON in Promptfoo without a model/grader."""

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report import loads_strict


def project(request):
    if set(request) != {"report", "sha256", "row"}:
        raise ValueError("expected report, sha256 and row")
    path = Path(request["report"])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("report must be an absolute regular file")
    raw = path.read_bytes()
    if len(raw) > 8_388_608 or hashlib.sha256(raw).hexdigest() != request["sha256"]:
        raise ValueError("report digest or size mismatch")
    data = loads_strict(raw.decode(), context="classification report")
    index = request["row"]
    if type(index) is not int or index < 0 or index >= len(data["rows"]):
        raise ValueError("invalid row index")
    return {"model_calls_by_provider": 0, "mode": "recorded-classification",
            "report_sha256": request["sha256"], "measurement": data,
            "row": data["rows"][index],
            "assertion_scope": "Transport equality only, not benchmark success"}


def config(report):
    path = report.resolve()
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    data = loads_strict(raw.decode(), context="classification report")
    if data.get("mode") not in {"finite-units", "canonical-holdout"} or not data.get("rows"):
        raise ValueError("expected classification measurement rows")
    tests = []
    for index, row in enumerate(data["rows"]):
        request = {"report": str(path), "sha256": digest, "row": index}
        expected = project(request)
        tests.append({"description": row["system"] + ": " + row["aggregation_unit"],
                      "vars": {"request": json.dumps(request)},
                      "assert": [{"type": "javascript", "value":
                          "const actual = JSON.parse(output);\nreturn JSON.stringify(actual) === JSON.stringify(" +
                          json.dumps(expected) + ");"}]})
    return {"description": "Classification display; assertion success is transport only",
            "sharing": False, "prompts": ["{{request}}"],
            "providers": [{"id": "exec:" + shlex.join(
                [sys.executable, str(Path(__file__).resolve()), "provider"]),
                "label": "Recorded measurements (no model/grader)"}],
            "tests": tests, "evaluateOptions": {"maxConcurrency": 1, "cache": False}}


def main():
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "provider":
            print(json.dumps(project(loads_strict(sys.argv[2], context="request"))))
            return 0
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--report", type=Path, required=True)
        parser.add_argument("--output", type=Path, required=True)
        args = parser.parse_args()
        result = config(args.report)
        with args.output.open("x") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
        return 0
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print(f"classification display: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Probe bundled Playwright reader eligibility without retaining report text."""

import argparse
import concurrent.futures
import json
import subprocess
from pathlib import Path


LAUNCHER = Path(__file__).resolve().parents[2] / "skills/playwright-debugger/scripts/run-artifact-reader.sh"


def probe(entry):
    path, report_sha = entry
    root = path.parent
    try:
        result = subprocess.run(
            [str(LAUNCHER), "--project-root", str(root), "--", "report", "--report-root", ".", path.name],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"report_sha256": report_sha, "status": "timeout"}
    if result.returncode == 0:
        try:
            records = json.loads(result.stdout)
            return {"report_sha256": report_sha, "status": "accepted", "abnormal_records": len(records)}
        except json.JSONDecodeError:
            return {"report_sha256": report_sha, "status": "invalid_reader_output"}
    stderr = result.stderr
    if "credential redaction left residual sensitive output" in stderr:
        reason = "residual_sensitive_output"
    elif "Playwright reporter outcome mismatch" in stderr:
        reason = "outcome_mismatch"
    elif "exceeds" in stderr or "too large" in stderr:
        reason = "size_or_shape_limit"
    else:
        reason = "other_reader_rejection"
    return {"report_sha256": report_sha, "status": "rejected", "reason": reason}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("acquisition", nargs="+", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite")
    entries = {}
    for acquisition in args.acquisition:
        source = json.loads(acquisition.read_text())
        for run in source["runs"]:
            for artifact in run.get("downloaded", []):
                root = args.cache / run["repository"].replace("/", "__") / str(run["run_id"]) / str(artifact["artifact_id"])
                for report in artifact.get("reports", []):
                    if "sha256" not in report:
                        continue
                    path = root / report["relative_path"]
                    entries.setdefault(report["sha256"], (path, report["sha256"]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(probe, entries.values()))
    tally = {}
    for result in results:
        key = result.get("reason", result["status"])
        tally[key] = tally.get(key, 0) + 1
    output = {"schema": "debugger-artifact-reader-probe-v1", "reports": len(results),
              "tally": tally, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"reports": len(results), "tally": tally}, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Freeze a privacy-minimal manifest of public CI failure observations.

This is an acquisition/eligibility manifest, not causal ground truth or an
accuracy score. Raw GitHub artifacts remain in the local cache.
"""

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    return digest(path.read_bytes())


def playwright_json_cases(path):
    source = json.loads(path.read_text())
    records = []
    for run in source["runs"]:
        for artifact in run.get("downloaded", []):
            for report in artifact.get("reports", []):
                for failure in report.get("failures", []):
                    records.append({
                        "repository": run["repository"], "run_id": run["run_id"],
                        "run_attempt": run["run_attempt"], "head_sha": run["head_sha"],
                        "run_url": run["html_url"], "artifact_id": artifact["artifact_id"],
                        "artifact_name": artifact["artifact_name"],
                        "report_sha256": report["sha256"],
                        "test_id_sha256": failure["test_id_sha256"],
                        "error_sha256": failure["error_sha256"],
                        "attempts": failure["attempts"], "report_kind": "playwright-json",
                    })
    return records


def blob_cases(path, run_id, artifact_id, head_sha):
    if path.stat().st_size > 64_000_000:
        raise ValueError("blob ZIP exceeds 64 MB")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        report_members = [member for member in members if member.filename == "report.jsonl"]
        if len(report_members) != 1 or report_members[0].file_size > 100_000_000:
            raise ValueError("blob must contain one bounded report.jsonl")
        latest = {}
        with archive.open(report_members[0]) as stream:
            for line in stream:
                event = json.loads(line)
                if event.get("method") != "onTestEnd":
                    continue
                test = event["params"]["test"]
                result = event["params"]["result"]
                latest[test["testId"]] = (test, result)
    records = []
    for test_id, (test, result) in latest.items():
        if test.get("expectedStatus") != "passed" or result["status"] not in ("failed", "timedOut"):
            continue
        records.append({
            "repository": "grafana/grafana", "run_id": run_id, "run_attempt": 1,
            "head_sha": head_sha, "run_url": f"https://github.com/grafana/grafana/actions/runs/{run_id}",
            "artifact_id": artifact_id, "artifact_name": "playwright-blob-8",
            "report_sha256": file_digest(path), "test_id_sha256": digest(test_id.encode()),
            "error_sha256": digest(json.dumps(result.get("errors", []), sort_keys=True).encode()),
            "attempts": None, "report_kind": "playwright-blob-jsonl",
        })
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--openmetadata", required=True, type=Path)
    parser.add_argument("--superset", required=True, type=Path)
    parser.add_argument("--grafana-blob", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite")
    records = playwright_json_cases(args.openmetadata) + playwright_json_cases(args.superset)
    json_count = len(records)
    records += blob_cases(args.grafana_blob, 37869069314, 11590026473,
                          "bf47b8f42ef10cfc36b7bc935ab0488763c3d48e")
    unique = {}
    for record in records:
        key = (record["repository"], record["run_id"], record["test_id_sha256"])
        unique.setdefault(key, record)
    frozen = sorted(unique.values(), key=lambda item: (item["repository"], item["run_id"], item["test_id_sha256"]))
    manifest = {
        "schema": "debugger-ci-artifacts-v1", "status": "ACQUISITION_ONLY_NO_CAUSAL_TRUTH",
        "input_sha256": {"openmetadata": file_digest(args.openmetadata),
                         "superset": file_digest(args.superset),
                         "grafana_blob": file_digest(args.grafana_blob)},
        "counts": {"raw_json_failure_records": json_count,
                   "raw_total_failure_records": len(records),
                   "duplicate_same_run_test_records": len(records) - len(frozen),
                   "unique_run_test_events": len(frozen),
                   "unique_repo_test_ids": len({(r["repository"], r["test_id_sha256"]) for r in frozen}),
                   "unique_repo_test_error_pairs": len({(r["repository"], r["test_id_sha256"], r["error_sha256"]) for r in frozen}),
                   "by_repository": dict(Counter(r["repository"] for r in frozen))},
        "cases": frozen,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["counts"], sort_keys=True))


if __name__ == "__main__":
    main()

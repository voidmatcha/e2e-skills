#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Select one reader-accepted observation per distinct CI test for source audit.

Writes sanitized reader excerpts to a private local cache, never to benchmarks/.
This does not assign root-cause truth or score a model.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


LAUNCHER = Path(__file__).resolve().parents[2] / "skills/playwright-debugger/scripts/run-artifact-reader.sh"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("acquisition", nargs="+", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite")
    manifest = json.loads(args.manifest.read_text())
    probe = json.loads(args.probe.read_text())
    accepted = {item["report_sha256"] for item in probe["results"] if item["status"] == "accepted"}
    locations = {}
    for source_file in args.acquisition:
        source = json.loads(source_file.read_text())
        for run in source["runs"]:
            for artifact in run.get("downloaded", []):
                root = (args.cache / run["repository"].replace("/", "__")
                        / str(run["run_id"]) / str(artifact["artifact_id"]))
                for report in artifact.get("reports", []):
                    if "sha256" in report:
                        locations[report["sha256"]] = root / report["relative_path"]
    representatives = {}
    for case in manifest["cases"]:
        if case["report_sha256"] not in accepted:
            continue
        key = (case["repository"], case["test_id_sha256"])
        if key not in representatives or case["run_id"] > representatives[key]["run_id"]:
            representatives[key] = case
    rows = []
    reader_cache = {}
    for (repository, test_hash), case in sorted(representatives.items()):
        path = locations[case["report_sha256"]]
        if path not in reader_cache:
            command = [str(LAUNCHER), "--project-root", str(path.parent), "--", "report",
                       "--report-root", ".", path.name]
            result = subprocess.run(command, cwd=path.parent, capture_output=True, text=True,
                                    check=True, timeout=30)
            reader_cache[path] = json.loads(result.stdout)
        matches = []
        for record in reader_cache[path]:
            identity = "\n".join((record.get("file", ""), record.get("title", ""),
                                  record.get("projectName", "")))
            if hashlib.sha256(identity.encode()).hexdigest() == test_hash:
                matches.append(record)
        if len(matches) != 1:
            raise ValueError(f"expected one reader record for {repository} {test_hash}; got {len(matches)}")
        record = matches[0]
        failed = [attempt for attempt in record["attempts"] if attempt["status"] in ("failed", "timedOut")]
        excerpt = str(failed[-1]["error"] or "")[:300] if failed else ""
        rows.append({"repository": repository, "test_id_sha256": test_hash,
                     "run_id": case["run_id"], "run_url": case["run_url"],
                     "head_sha": case["head_sha"], "report_sha256": case["report_sha256"],
                     "file": record["file"], "title": record["title"],
                     "project_name": record["projectName"], "outcome": record["outcome"],
                     "attempt_statuses": [attempt["status"] for attempt in record["attempts"]],
                     "sanitized_error_excerpt": excerpt})
    output = {"schema": "debugger-ci-validation-candidates-v1", "status": "UNADJUDICATED",
              "source_manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
              "candidates": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"reader_accepted_distinct_tests": len(rows),
                      "excluded_blob_or_reader_rejected": manifest["counts"]["unique_repo_test_ids"] - len(rows)}))


if __name__ == "__main__":
    main()

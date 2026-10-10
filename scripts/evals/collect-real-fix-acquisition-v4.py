#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect the frozen v4 public GitHub commit windows without assigning labels."""

import argparse
import json
import re
import subprocess
from pathlib import Path


ROWS = (
    ("mtlynch/whatgotdone", "ef10be2a9f8a57c35f67d299a4c0ef374e768e04", "e2e", r"^e2e/.*\.spec\.ts$"),
    ("RedHatInsights/patchman-ui", "9b6bac02e02373d6a8ad99a1920b19ab1fd23979", "playwright", r"^playwright/(?:Integration|UI)/.*\.spec\.ts$"),
    ("xmlui-org/xmlui", "e4e2bc10dadb630105fc4d33f4f8b59cf3a30ea3", "xmlui/tests-e2e", r"^xmlui/tests-e2e/.*\.spec\.ts$"),
    ("godotlauncher/launcher", "e26cdb8daf289aada48b9e57e58bdbe02f681c3a", "e2e", r"^e2e/.*\.spec\.ts$"),
    ("verdaccio/verdaccio", "8f877d52abb8f37f3b4eacd7917dad8299544034", "cypress/e2e", r"^cypress/e2e/.*\.cy\.ts$"),
    ("victronenergy/venus-html5-app", "61f4dd8c6f339a4ec025d3af4d39a90cb81c4ea7", "cypress/e2e", r"^cypress/e2e/.*\.spec\.ts$"),
    ("wikimedia/wikidata-query-builder", "d2b960af9b6417ce2c9c32d224671d5988d5ad37", "cypress/e2e", r"^cypress/e2e/.*\.cy\.js$"),
    ("ministryofjustice/hmpps-contacts-ui", "aee67b0a2d258ba03d508cea0f4f8372772388eb", "integration_tests/e2e", r"^integration_tests/e2e/.*\.cy\.[jt]sx?$"),
)


def gh_api(endpoint: str) -> object:
    result = subprocess.run(["gh", "api", endpoint], check=True, capture_output=True, text=True, timeout=60)
    return json.loads(result.stdout)


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    report = {"protocol": "real-fix-acquisition-v4", "status": "INCOMPLETE", "repositories": []}
    save(args.output, report)
    try:
        for name, cutoff, path, spec_regex in ROWS:
            endpoint = f"repos/{name}/commits?sha={cutoff}&path={path}&per_page=25"
            listed = gh_api(endpoint)
            if not isinstance(listed, list) or len(listed) > 25:
                raise ValueError(f"invalid commit list for {name}")
            row = {"name": name, "cutoff": cutoff, "path": path, "endpoint": endpoint,
                   "returned_commits": len(listed), "commits": []}
            report["repositories"].append(row)
            spec_pattern = re.compile(spec_regex)
            save(args.output, report)
            for ordinal, item in enumerate(listed, 1):
                sha = item["sha"]
                detail = gh_api(f"repos/{name}/commits/{sha}")
                files = detail.get("files", [])
                incomplete_files = len(files) >= 300
                spec_files = [
                    {"path": file["filename"], "status": file["status"],
                     "previous_filename": file.get("previous_filename")}
                    for file in files if spec_pattern.search(file["filename"])
                ]
                row["commits"].append({
                    "ordinal": ordinal,
                    "sha": sha,
                    "parents": [parent["sha"] for parent in detail["parents"]],
                    "subject": item["commit"]["message"].splitlines()[0],
                    "changed_files": len(files),
                    "spec_files": spec_files,
                    "disposition": "file-list-possibly-truncated" if incomplete_files else (
                        "pending-source" if spec_files else "no-spec-change"),
                })
                save(args.output, report)
                print(f"{name} {ordinal}/{len(listed)} {sha[:10]} {row['commits'][-1]['disposition']}", flush=True)
        report["status"] = "COMPLETE"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        save(args.output, report)
        raise
    save(args.output, report)


if __name__ == "__main__":
    main()

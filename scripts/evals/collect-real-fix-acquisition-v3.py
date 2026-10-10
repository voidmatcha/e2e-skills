#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect the frozen public GitHub commit windows for real-fix acquisition v3.

Read-only source metadata collection; never labels a defect or runs the product.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path


ROWS = (
    ("calcom/cal.com", "e91bb0c38251b0ee6f87eec70ce4940822fb0cf3", "apps/web/playwright", r"^apps/web/playwright/.*\.e2e\.[jt]sx?$"),
    ("element-hq/hydrogen-web", "ea5976e40b8d4974890e67bba3c139012044612c", "playwright/tests", r"^playwright/tests/.*\.spec\.[jt]sx?$"),
    ("officecli/officedex", "60d199dad7951e9ba688ec9bac2ebaf10323c752", "e2e", r"^e2e/.*\.spec\.[jt]sx?$"),
    ("RedHatInsights/uhc-portal", "5ccaadbf025ae035bf2d95a8f4716102f6e63303", "cypress/e2e", r"^cypress/e2e/.*\.js$"),
    ("tomosterlund/qalendar", "1e81b86d45a4e34be7b7c8bc59fa17aea713d890", "cypress/e2e", r"^cypress/e2e/.*\.cy\.[jt]sx?$"),
    ("xchem/fragalysis-frontend", "c5a0cd68d30fcbb34dd66dfccedd9f41fb571648", "cypress/e2e", r"^cypress/e2e/.*\.cy\.[jt]sx?$"),
)


def gh_api(endpoint: str) -> object:
    response = subprocess.run(
        ["gh", "api", endpoint],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(response.stdout)


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    report = {"protocol": "real-fix-acquisition-v3", "status": "INCOMPLETE", "repositories": []}
    save(args.output, report)
    try:
        for name, cutoff, path, spec_pattern in ROWS:
            endpoint = f"repos/{name}/commits?sha={cutoff}&path={path}&per_page=25"
            listed = gh_api(endpoint)
            if not isinstance(listed, list) or len(listed) > 25:
                raise ValueError(f"invalid commit list for {name}")
            row = {"name": name, "cutoff": cutoff, "path": path, "endpoint": endpoint,
                   "returned_commits": len(listed), "commits": []}
            report["repositories"].append(row)
            pattern = re.compile(spec_pattern)
            save(args.output, report)
            for ordinal, item in enumerate(listed, 1):
                sha = item["sha"]
                detail = gh_api(f"repos/{name}/commits/{sha}")
                files = detail.get("files", [])
                incomplete_files = len(files) >= 300
                spec_files = [
                    {"path": file["filename"], "status": file["status"],
                     "previous_filename": file.get("previous_filename")}
                    for file in files if pattern.search(file["filename"])
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

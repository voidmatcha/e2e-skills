#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record the fixed GitHub commit windows for real-fix acquisition v2.

Read-only public GitHub API calls through the agent-reach gh fallback. This
collector does not label defects, run a scanner, or inspect model outcomes.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path


REPOSITORIES = (
    ("OHIF/Viewers", "f06cf8b309551325038a80d38c2ec94af81d79ae", "tests", r"^tests/.*\.spec\.[jt]sx?$"),
    ("ever-co/ever-gauzy", "54b537baf8755924eb11f0505b99c304e6b44c8a", "apps/gauzy-e2e/tests", r"^apps/gauzy-e2e/tests/.*\.spec\.[jt]sx?$"),
    ("harvester/tests", "fe06844ce0f38a4b3a438085c436dad3c51e464c", "cypress/testcases", r"^cypress/testcases/.*\.spec\.[jt]sx?$"),
    ("omegaup/omegaup", "26730787a588243308602da544f5be2fc009ceff", "cypress/e2e", r"^cypress/e2e/.*\.cy\.[jt]sx?$"),
)


def gh_api(endpoint: str) -> object:
    result = subprocess.run(
        ["gh", "api", endpoint],
        check=True,
        capture_output=True,
        text=True,
        timeout=45,
    )
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite")

    report = {"protocol": "real-fix-acquisition-v2", "status": "INCOMPLETE", "repositories": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for name, cutoff, path, spec_pattern in REPOSITORIES:
        endpoint = f"repos/{name}/commits?sha={cutoff}&path={path}&per_page=25"
        listed = gh_api(endpoint)
        if not isinstance(listed, list) or len(listed) != 25:
            raise RuntimeError(f"expected exactly 25 commits for {name}; got {len(listed)}")
        repo = {"name": name, "cutoff": cutoff, "path": path, "endpoint": endpoint, "commits": []}
        report["repositories"].append(repo)
        pattern = re.compile(spec_pattern)
        for ordinal, item in enumerate(listed, 1):
            sha = item["sha"]
            detail = gh_api(f"repos/{name}/commits/{sha}")
            files = detail.get("files", [])
            if len(files) >= 300:
                disposition = "file-list-possibly-truncated"
            else:
                disposition = "pending-source" if any(pattern.search(file["filename"]) for file in files) else "no-spec-change"
            row = {
                "ordinal": ordinal,
                "sha": sha,
                "parents": [parent["sha"] for parent in detail["parents"]],
                "subject": item["commit"]["message"].splitlines()[0],
                "changed_files": len(files),
                "spec_files": [
                    {"path": file["filename"], "status": file["status"],
                     "previous_filename": file.get("previous_filename")}
                    for file in files if pattern.search(file["filename"])
                ],
                "disposition": disposition,
            }
            repo["commits"].append(row)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
            print(f"{name} {ordinal}/25 {sha[:10]} {disposition}", flush=True)
    report["status"] = "COMPLETE"
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

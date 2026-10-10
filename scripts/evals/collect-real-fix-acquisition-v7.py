#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect the frozen v7 merged-PR search positions without labels."""

import argparse
import json
import subprocess
from pathlib import Path
from urllib.parse import quote


QUERIES = (
    ("PW-old-title", "is:pr is:merged playwright flaky in:title created:2023-01-01..2024-12-31"),
    ("CY-old-title", "is:pr is:merged cypress flaky in:title created:2023-01-01..2024-12-31"),
)


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    report = {"protocol": "real-fix-acquisition-v7", "status": "INCOMPLETE", "query_rows": []}
    save(args.output, report)
    seen = {}
    try:
        for label, query in QUERIES:
            endpoint = f"search/issues?q={quote(query, safe='')}&sort=created&order=desc&per_page=20"
            result = subprocess.run(["gh", "api", endpoint], check=True, capture_output=True, text=True, timeout=60)
            payload = json.loads(result.stdout)
            items = payload["items"]
            if not isinstance(items, list) or len(items) > 20:
                raise ValueError(f"invalid search result for {label}")
            row = {"label": label, "query": query, "endpoint": endpoint,
                   "total_count": payload["total_count"], "returned_prs": len(items), "prs": []}
            report["query_rows"].append(row)
            for ordinal, item in enumerate(items, 1):
                repo = item["repository_url"].split("/repos/", 1)[1]
                key = (repo, item["number"])
                row["prs"].append({
                    "ordinal": ordinal,
                    "repository": repo,
                    "number": item["number"],
                    "url": item["html_url"],
                    "title": item["title"],
                    "created_at": item["created_at"],
                    "closed_at": item["closed_at"],
                    "duplicate_of": seen.get(key),
                    "disposition": "duplicate" if key in seen else "pending-source",
                })
                seen.setdefault(key, f"{label}:{ordinal}")
            save(args.output, report)
            print(f"{label}: {len(items)} positions, {payload['total_count']} search matches", flush=True)
        report["status"] = "COMPLETE"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        save(args.output, report)
        raise
    save(args.output, report)


if __name__ == "__main__":
    main()

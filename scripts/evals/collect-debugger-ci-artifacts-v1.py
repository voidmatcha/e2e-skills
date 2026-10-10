#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inventory and optionally download bounded public Playwright CI reports.

Only read-only GitHub API/download calls are made. Raw reports stay outside the
repository; the output contains provenance and hashes, not failure messages.
"""

import argparse
import concurrent.futures
import hashlib
import io
import json
import re
import stat
import subprocess
import sys
import zipfile
from pathlib import Path


SOURCES = (
    ("open-metadata/OpenMetadata", 102327654, r"^playwright-results-json-", 3_000_000),
    ("apache/superset", 1024928, r"^playwright-artifact-", 100_000_000),
)


def api(endpoint):
    call = subprocess.run(["gh", "api", endpoint], text=True, capture_output=True, timeout=60, check=True)
    return json.loads(call.stdout)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def failures(report):
    pending = list(report.get("suites", []))
    found = []
    while pending:
        suite = pending.pop()
        pending.extend(suite.get("suites", []))
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                if test.get("status") != "unexpected":
                    continue
                messages = []
                for result in test.get("results", []):
                    for error in result.get("errors", []):
                        messages.append(error.get("message", ""))
                identity = "\n".join((suite.get("file", ""), spec.get("title", ""), test.get("projectName", "")))
                found.append({
                    "test_id_sha256": hashlib.sha256(identity.encode()).hexdigest(),
                    "error_sha256": hashlib.sha256("\n".join(messages).encode()).hexdigest(),
                    "attempts": len(test.get("results", [])),
                })
    return found


def inventory(source, limit):
    repository, workflow, name_pattern, max_bytes = source
    runs = api(f"repos/{repository}/actions/workflows/{workflow}/runs?status=failure&per_page={limit}")["workflow_runs"]

    def row(run):
        artifacts = api(f"repos/{repository}/actions/runs/{run['id']}/artifacts?per_page=100")["artifacts"]
        eligible = [
            {"id": artifact["id"], "name": artifact["name"], "size_in_bytes": artifact["size_in_bytes"],
             "expired": artifact["expired"], "created_at": artifact["created_at"]}
            for artifact in artifacts
            if re.search(name_pattern, artifact["name"])
            and not artifact["expired"] and artifact["size_in_bytes"] <= max_bytes
        ]
        return {"repository": repository, "workflow_id": workflow, "run_id": run["id"],
                "run_attempt": run["run_attempt"], "head_sha": run["head_sha"],
                "created_at": run["created_at"], "html_url": run["html_url"],
                "eligible_artifacts": eligible}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(row, runs))


def download(row, artifact, root):
    destination = root / row["repository"].replace("/", "__") / str(row["run_id"]) / str(artifact["id"])
    if not destination.exists() or not any(destination.rglob("results.json")):
        destination.mkdir(parents=True)
        endpoint = f"repos/{row['repository']}/actions/artifacts/{artifact['id']}/zip"
        fetched = subprocess.run(["gh", "api", endpoint], capture_output=True, check=True, timeout=120)
        if len(fetched.stdout) > artifact["size_in_bytes"] + 1024 or len(fetched.stdout) > 100_000_000:
            raise ValueError("artifact ZIP exceeds declared/bounded size")
        with zipfile.ZipFile(io.BytesIO(fetched.stdout)) as archive:
            members = archive.infolist()
            if len(members) > 10_000:
                raise ValueError("artifact ZIP has too many members")
            names = set()
            report_count = 0
            extracted_bytes = 0
            for member in members:
                parts = member.filename.split("/")
                if (member.filename.startswith("/") or "\\" in member.filename
                        or any(part in ("", ".", "..") for part in parts if not member.is_dir())
                        or member.filename.casefold() in names):
                    raise ValueError("artifact ZIP has unsafe/duplicate member name")
                names.add(member.filename.casefold())
                mode = member.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError("artifact ZIP has special member")
                if member.filename.rsplit("/", 1)[-1] != "results.json":
                    continue
                if member.is_dir() or member.file_size > 20_000_000:
                    raise ValueError("artifact report exceeds 20 MB")
                report_count += 1
                extracted_bytes += member.file_size
                if report_count > 5 or extracted_bytes > 40_000_000:
                    raise ValueError("artifact has too many/large reports")
                target = destination.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as stream:
                    data = stream.read(20_000_001)
                if len(data) != member.file_size or len(data) > 20_000_000:
                    raise ValueError("artifact report length mismatch")
                target.write_bytes(data)
    reports = []
    for path in sorted(destination.rglob("results.json")):
        if path.stat().st_size > 20_000_000:
            continue
        try:
            report = json.loads(path.read_text())
            if "suites" not in report or "stats" not in report:
                continue
            reports.append({"relative_path": str(path.relative_to(destination)), "sha256": sha256(path),
                            "size_in_bytes": path.stat().st_size, "stats": report["stats"],
                            "failures": failures(report)})
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            reports.append({"relative_path": str(path.relative_to(destination)), "parse_error": type(error).__name__})
    return {"artifact_id": artifact["id"], "artifact_name": artifact["name"], "reports": reports}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--source", choices=[source[0] for source in SOURCES])
    parser.add_argument("--max-runs", type=int)
    parser.add_argument("--runs-per-source", type=int, default=100)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--target-failures", type=int, default=100)
    parser.add_argument("--target-unique-tests", type=int)
    parser.add_argument("--max-download-bytes", type=int, default=1_000_000_000)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite")
    if not 1 <= args.runs_per_source <= 100:
        parser.error("runs-per-source must be between 1 and 100")
    if args.inventory:
        prior = json.loads(args.inventory.read_text())
        if prior.get("schema") != "debugger-ci-artifact-acquisition-v1" or prior.get("status") != "INVENTORY_ONLY":
            parser.error("inventory must be a v1 inventory-only report")
        rows = prior["runs"]
    else:
        rows = []
        for source in SOURCES:
            rows.extend(inventory(source, args.runs_per_source))
    if args.source:
        rows = [row for row in rows if row["repository"] == args.source]
    if args.max_runs is not None:
        rows = rows[:args.max_runs]
    report = {"schema": "debugger-ci-artifact-acquisition-v1", "status": "INVENTORY_ONLY", "runs": rows}
    if args.download:
        report["status"] = "IN_PROGRESS"
        remaining = args.max_download_bytes
        total_failures = 0
        unique_tests = set()
        for row in rows:
            row["downloaded"] = []
            for artifact in row["eligible_artifacts"]:
                if artifact["size_in_bytes"] > remaining:
                    continue
                remaining -= artifact["size_in_bytes"]
                try:
                    row["downloaded"].append(download(row, artifact, args.cache))
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, zipfile.BadZipFile) as error:
                    row["downloaded"].append({"artifact_id": artifact["id"], "download_error": type(error).__name__})
            count = sum(len(item.get("failures", [])) for entry in row["downloaded"] for item in entry.get("reports", []))
            total_failures += count
            unique_tests.update(failure["test_id_sha256"] for entry in row["downloaded"]
                                for item in entry.get("reports", []) for failure in item.get("failures", []))
            if count:
                print(f"{row['repository']} run {row['run_id']}: {count} unexpected tests", file=sys.stderr, flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            if (args.target_unique_tests is not None and len(unique_tests) >= args.target_unique_tests) or (
                args.target_unique_tests is None and total_failures >= args.target_failures
            ):
                break
        report["status"] = "DOWNLOADED"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "runs": len(rows),
                      "eligible_artifacts": sum(len(row["eligible_artifacts"]) for row in rows),
                      "downloaded_artifacts": sum(len(row.get("downloaded", [])) for row in rows),
                      "unexpected_tests": sum(len(item.get("failures", [])) for row in rows
                                              for entry in row.get("downloaded", []) for item in entry.get("reports", []))}))


if __name__ == "__main__":
    main()

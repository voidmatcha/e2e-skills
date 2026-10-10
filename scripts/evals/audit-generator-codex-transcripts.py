#!/usr/bin/env python3
"""Post-hoc event audit; never changes frozen reports. Apache-2.0."""
import argparse
import hashlib
import json
import re
from pathlib import Path

FAILURES = {
    "preflight_connection_refused": re.compile(r"preflight_target: pinned probe failed.*curl exit 7", re.S),
    "missing_default_chrome": re.compile(r"Chromium distribution 'chrome' is not found"),
    "port_in_use": re.compile(r"EADDRINUSE"),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(report_path, transcript_root):
    report = json.loads(report_path.read_text())
    totals, files = {}, []
    seen_calls = set()
    for row in report["runs"]:
        if row["call_id"] in seen_calls:
            raise ValueError("duplicate call")
        seen_calls.add(row["call_id"])
        counts = {key: 0 for key in (*FAILURES, "spawn_agent_events", "invalid_json_lines")}
        for attempt in row["attempts"]:
            path = transcript_root / Path(attempt["transcript_path"]).name
            if path.is_symlink() or not path.is_file():
                raise ValueError("missing or symlinked transcript")
            local = dict.fromkeys(counts, 0)
            for line in path.read_text().splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    local["invalid_json_lines"] += 1
                    continue
                if not isinstance(event, dict) or event.get("type") != "item.completed":
                    continue
                item = event.get("item", {})
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "collab_tool_call" and item.get("tool") == "spawn_agent":
                    local["spawn_agent_events"] += 1
                if item.get("type") == "command_execution" and item.get("exit_code") not in (None, 0):
                    output = item.get("aggregated_output", "")
                    if not isinstance(output, str):
                        continue
                    for key, pattern in FAILURES.items():
                        local[key] += bool(pattern.search(output))
            for key, value in local.items():
                counts[key] += value
            files.append({"call_id": row["call_id"], "attempt": attempt.get("attempt"),
                          "infrastructure_error": bool(attempt.get("infrastructure_error")),
                          "file": path.name, "sha256": sha(path), "counts": local})
        arm = totals.setdefault(row["arm"], {"calls": 0, **{
            key: {"events": 0, "calls": 0} for key in counts
        }})
        arm["calls"] += 1
        for key, value in counts.items():
            arm[key]["events"] += value
            arm[key]["calls"] += bool(value)
    return {
        "kind": "post_hoc_parent_event_audit",
        "report_sha256": sha(report_path),
        "scored_calls": len(seen_calls),
        "attempts": len(files),
        "infrastructure_error_attempts": sum(file["infrastructure_error"] for file in files),
        "arms": totals,
        "transcripts": files,
        "limits": [
            "Invalid sanitized JSONL lines are counted and skipped, not repaired.",
            "Parent tool events do not prove child correctness, V4/V6 compliance, or billed USD.",
            "Observed failures do not quantify the savings from repairing the environment.",
            "Transcript originals remain outside the public archive; hashes permit local verification.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("transcripts", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to replace an existing audit")
    data = audit(args.report, args.transcripts)
    args.output.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()

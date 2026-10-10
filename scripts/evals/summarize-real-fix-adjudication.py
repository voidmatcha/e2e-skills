#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check source-adjudication coverage and summarize the cross-model extra findings."""

import argparse
import collections
import hashlib
import json
from pathlib import Path


VERDICTS = {"CONFIRMED", "FALSE_POSITIVE", "NEEDS_CONTEXT", "INVALID_LOCATION"}
ARMS = ("full", "catalog-only", "no-skill")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(case: str, side: str, finding: dict) -> tuple:
    return case, side, finding["file"], finding["line"], finding["pattern_id"]


def extras(call: dict) -> list[tuple]:
    scored = call["score"]
    target = scored.get("target_findings", []) + scored.get("mapped_after_alarms", [])
    target_multiset = collections.Counter(
        key(call["case"], call["side"], item) for item in target
    )
    remaining = []
    for finding in call["answer"]["findings"]:
        identity = key(call["case"], call["side"], finding)
        if target_multiset[identity]:
            target_multiset[identity] -= 1
        else:
            remaining.append(identity)
    if sum(target_multiset.values()):
        raise ValueError("target finding absent from raw answer")
    if len(remaining) != scored["other_findings_unadjudicated"]:
        raise ValueError("extra-finding count drift")
    return remaining


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sol", required=True, type=Path)
    parser.add_argument("--astra", required=True, type=Path)
    parser.add_argument("--claude", required=True, type=Path)
    parser.add_argument("--ledgers", required=True, nargs="+", type=Path)
    args = parser.parse_args()
    reports = {name: json.loads(path.read_text()) for name, path in (
        ("sol", args.sol), ("astra", args.astra), ("claude", args.claude)
    )}
    observations = collections.defaultdict(list)
    for model, report in reports.items():
        if report["status"] != "COMPLETE":
            raise ValueError(f"incomplete report: {model}")
        selected = [call for call in report["calls"] if call["case"] != "datagrok"]
        if len(selected) != 30 or not all(call["complete"] for call in selected):
            raise ValueError(f"incomplete five-case calls: {model}")
        for call in selected:
            for identity in extras(call):
                observations[identity].append((model, call["arm"]))

    ledgers = {}
    for path in args.ledgers:
        ledger = json.loads(path.read_text())
        if ledger["status"] != "COMPLETE":
            raise ValueError(f"incomplete ledger: {path}")
        for row in ledger["rows"]:
            identity = key(row["case"], row["side"], row)
            if identity in ledgers:
                raise ValueError(f"duplicate adjudication: {identity}")
            if row["verdict"] not in VERDICTS or not row.get("reason") or not row.get("evidence"):
                raise ValueError(f"invalid or unsupported verdict: {identity}")
            ledgers[identity] = row
    missing = set(observations) - set(ledgers)
    surplus = set(ledgers) - set(observations)
    if missing or surplus:
        raise ValueError(f"ledger coverage mismatch: {len(missing)} missing, {len(surplus)} surplus")

    counts = {}
    for model in reports:
        counts[model] = {}
        for arm in ARMS:
            relevant = [ledgers[identity]["verdict"]
                        for identity, occurrences in observations.items()
                        for observed_model, observed_arm in occurrences
                        if (observed_model, observed_arm) == (model, arm)]
            counts[model][arm] = dict(collections.Counter(relevant))
    summary = {
        "status": "COMPLETE",
        "claim": "source-adjudicated extra-prediction counts on the five public development clusters",
        "unique_keys": len(observations),
        "raw_extra_predictions": sum(map(len, observations.values())),
        "unique_verdicts": dict(collections.Counter(row["verdict"] for row in ledgers.values())),
        "per_model_arm_predictions": counts,
        "report_sha256": {name: digest(path) for name, path in (
            ("sol", args.sol), ("astra", args.astra), ("claude", args.claude)
        )},
        "ledger_sha256": {path.name: digest(path) for path in args.ledgers},
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

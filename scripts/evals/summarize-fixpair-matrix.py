#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarize paired fixpair runs without changing their archived Inspect scores.

Usage: summarize-fixpair-matrix.py MANIFEST RUN_ROOT PREFIX [--models sol astra sonnet]
       [--prefix-by-model sonnet=runs-current-200c]
       [--acknowledge-aux-leak-fp SAMPLE=EVENTS_SHA256]
Each run directory is PREFIX-MODEL-BATCH-ARM with one completed .eval log.
"""

import argparse
import importlib.util
import json
import random
import zipfile
from collections import defaultdict
from pathlib import Path


AUDIT = Path(__file__).with_name("audit-fixpair-logs.py")
spec = importlib.util.spec_from_file_location("fixpair_audit", AUDIT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

ARMS = ("skill", "no-skill")
BATCHES = ("B", "C", "D")
EXCLUDE_UNSUPPORTED = {
    "backst-daaaa72e-9b7887-before",
    "storyb-613551da-06aa67-before",
}
EXCLUDE_RISK_ONLY = {
    "backst-02a0f0df-27e82e-before",
    "backst-daaaa72e-38c493-before",
}


def read_run(root, prefix, model, batch, arm, acknowledged_leak_fps=None):
    acknowledged_leak_fps = acknowledged_leak_fps or {}
    folder = root / f"{prefix}-{model}-{batch.lower()}-{arm}"
    manifest = json.loads((folder / "run-manifest.json").read_text())
    assert manifest["arm"] == arm and manifest["batch"] == batch
    assert manifest["epochs"] == 1 and manifest["limit"] is None
    logs = list((folder / "inspect-logs").glob("*.eval"))
    assert len(logs) == 1, f"expected one log in {folder}, found {len(logs)}"
    with zipfile.ZipFile(logs[0]) as archive:
        header = json.loads(archive.read("header.json"))
        assert header["status"] == "success", f"{folder}: {header['status']}"
        names = {name for name in archive.namelist()
                 if name.startswith("samples/") and name.endswith(".json")}
        samples = [json.loads(archive.read(name)) for name in sorted(names)]
    by_id = {}
    for sample in samples:
        item = sample["metadata"]
        assert item["batch"] == batch and item["arm"] == arm
        assert item["returncode"] == 0
        if item["leak_reads"]:
            event_log = Path(item["cell"]) / "events.jsonl"
            assert item["leak_reads"] == 1
            assert acknowledged_leak_fps.get(item["id"]) == audit_sha(event_log), (
                f"unadjudicated auxiliary leak metric in {folder}: {item['id']}")
        assert sample["epoch"] == 1 and not sample.get("error_retries")
        key = item["id"]
        assert key not in by_id, f"duplicate sample {key}"
        by_id[key] = sample
    assert header["results"]["completed_samples"] == len(by_id)
    return manifest, by_id, header


def row_for(sample):
    meta = sample["metadata"]
    corrected = audit.score(sample, True)
    score_name = "strict_recall" if meta["side"] == "before" else "after_false_alarm"
    original = sample["scores"][score_name]["value"]
    key = "hits" if meta["side"] == "before" else "alarms"
    assert sum(item["hit"] for item in corrected) == original[key]
    return {
        "batch": meta["batch"], "case": meta["case"], "sample": meta["id"],
        "side": meta["side"], "hits": [int(item["hit"]) for item in corrected],
        "patterns": [item["pattern"] for item in corrected],
        "input_tokens": meta["input_tokens"], "seconds": meta["seconds"],
        "calls": meta["calls"],
    }


def totals(rows, excluded):
    selected = [row for row in rows.values()
                if row["sample"] not in excluded]
    before = [row for row in selected if row["side"] == "before"]
    after = [row for row in selected if row["side"] == "after"]
    return {
        "strict_hits": sum(sum(row["hits"]) for row in before),
        "before_labels": sum(len(row["hits"]) for row in before),
        "after_alarms": sum(sum(row["hits"]) for row in after),
        "after_labels": sum(len(row["hits"]) for row in after),
    }


def bootstrap_delta(skill, baseline, excluded, draws=10000):
    paired = defaultdict(list)
    for sample_id, left in skill.items():
        if left["side"] != "before" or sample_id in excluded:
            continue
        right = baseline[sample_id]
        assert len(left["hits"]) == len(right["hits"])
        paired[left["case"]].extend(zip(left["hits"], right["hits"]))
    cases = sorted(paired)
    rng = random.Random(20261002)
    deltas = []
    for _ in range(draws):
        pairs = [pair for case in rng.choices(cases, k=len(cases))
                 for pair in paired[case]]
        deltas.append(sum(a - b for a, b in pairs) / len(pairs))
    deltas.sort()
    return [round(deltas[int(draws * 0.025)], 4),
            round(deltas[int(draws * 0.975)], 4)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("prefix")
    parser.add_argument("--models", nargs="+", default=["sol", "astra", "sonnet"])
    parser.add_argument("--prefix-by-model", action="append", default=[], metavar="MODEL=PREFIX")
    parser.add_argument("--acknowledge-aux-leak-fp", action="append", default=[],
                        metavar="SAMPLE=EVENTS_SHA256")
    args = parser.parse_args()
    prefixes = dict(item.split("=", 1) for item in args.prefix_by_model)
    acknowledged_leak_fps = dict(item.split("=", 1) for item in args.acknowledge_aux_leak_fp)
    assert all(model and prefix for model, prefix in prefixes.items())
    assert all(sample and len(digest) == 64 for sample, digest in acknowledged_leak_fps.items())
    corpus = json.loads(args.manifest.read_text())
    expected = {s["id"] for s in corpus["samples"] if s["batch"] in BATCHES}
    reports = {}
    common = None
    skill_head = None
    task_shas = {}
    seen_acknowledged = set()
    for model in args.models:
        by_arm = {arm: {} for arm in ARMS}
        for batch in BATCHES:
            for arm in ARMS:
                run, samples, header = read_run(
                    args.run_root, prefixes.get(model, args.prefix), model, batch, arm,
                    acknowledged_leak_fps)
                seen_acknowledged.update(
                    key for key, value in samples.items()
                    if value["metadata"]["leak_reads"])
                assert run["manifest_sha256"] == audit_sha(args.manifest)
                identity = (run["skill_repo"], run["skill_git_head"] if arm == "skill" else None,
                            run["legend_sha256"], run["holdout_sha256"], run["task_sha256"])
                if common is None:
                    common = identity[0], identity[2], identity[3]
                assert (identity[0], identity[2], identity[3]) == common
                if model in task_shas:
                    assert identity[4] == task_shas[model]
                else:
                    task_shas[model] = identity[4]
                if arm == "skill":
                    if skill_head is None:
                        skill_head = identity[1]
                    assert identity[1] == skill_head
                assert not (set(samples) & set(by_arm[arm]))
                by_arm[arm].update({key: row_for(value) for key, value in samples.items()})
        for arm in ARMS:
            assert set(by_arm[arm]) == expected, f"{model}/{arm}: incomplete corpus"
        assert set(by_arm["skill"]) == set(by_arm["no-skill"])
        report = {}
        for label, excluded_before in (
            ("frozen_33", set()),
            ("source_audited_31", EXCLUDE_UNSUPPORTED),
            ("without_10c_risks_29", EXCLUDE_UNSUPPORTED | EXCLUDE_RISK_ONLY),
        ):
            excluded = excluded_before | {item.replace("-before", "-after")
                                          for item in excluded_before}
            report[label] = {arm: totals(rows, excluded) for arm, rows in by_arm.items()}
            report[label]["recall_delta_ci95"] = bootstrap_delta(
                by_arm["skill"], by_arm["no-skill"], excluded)
        report["resources"] = {
            arm: {
                "input_tokens": sum(row["input_tokens"] for row in rows.values()),
                "sum_call_seconds": round(sum(row["seconds"] for row in rows.values()), 1),
                "tool_calls": sum(row["calls"] for row in rows.values()),
            }
            for arm, rows in by_arm.items()
        }
        reports[model] = report
    assert seen_acknowledged == set(acknowledged_leak_fps), (
        "unused auxiliary leak metric acknowledgement")
    print(json.dumps({"provenance": {
        "manifest_sha256": audit_sha(args.manifest),
        "skill_repo": common[0], "skill_git_head": skill_head,
        "legend_sha256": common[1], "holdout_sha256": common[2],
        "task_sha256_by_model": task_shas,
        "acknowledged_aux_leak_metric_false_positives": acknowledged_leak_fps,
    }, "models": reports}, indent=2))


def audit_sha(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()

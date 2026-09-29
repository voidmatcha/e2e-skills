#!/usr/bin/env python3
"""Protect the frozen, superseded reviewer-specificity-v1 protocol."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v1.json"
SUCCESSOR_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v2.json"
README_PATH = ROOT / "benchmarks/reviewer-specificity-v1/README.md"
SUCCESSOR_README_PATH = ROOT / "benchmarks/reviewer-specificity-v2/README.md"
RECORDED_PROTOCOL_SHA256 = "c3d8c035f40be955647ab552dfa934949a9098e35a6185ae5fea317e1f7a19fc"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_module("specificity_runner", RUNNER_PATH)
COMPARATOR = load_module("specificity_comparator", COMPARATOR_PATH)
PROTOCOL = RUNNER.load_protocol(PROTOCOL_PATH)


def cases(count=24):
    return [{
        "id": f"case-{index:02d}",
        "framework": "playwright" if index % 2 == 0 else "cypress",
        "split": "holdout", "source_files": [{"source": "unused", "path": "spec.ts"}],
        "labels": [{"finding_id": f"guard-{index:02d}", "kind": "fp_guard",
                    "pattern_id": "#1", "severity": "P0", "file": "spec.ts",
                    "line": 1, "source_line": "test"}],
    } for index in range(count)]


def finding(line=2):
    return {"pattern_id": "#1", "severity": "P0", "file": "spec.ts", "line": line}


def report(profile, corpus, finding_repetitions=()):
    runs = []
    for case in corpus:
        for repetition in range(1, 4):
            findings = [finding()] if repetition in finding_repetitions else []
            runs.append({"case": case["id"], "findings": findings,
                         "score": {"tp": 0, "fp": len(findings), "fn": 0}})
    primary, secondary = RUNNER.specificity_metrics(corpus, runs, PROTOCOL)
    return {"prompt_profile": profile, "runner": "codex", "model": "gpt-5.6-sol",
            "protocol_id": PROTOCOL["protocol_id"],
            "status": "PASS", "complete": True, "execution_complete": True,
            "primary_metrics": primary, "secondary_metrics": secondary, "runs": runs}


def arm_reports(corpus):
    return {"full": [report("full", corpus)],
            "catalog-only": [report("catalog-only", corpus, {1, 2, 3})],
            "no-skill": [report("no-skill", corpus, {1, 2, 3})]}


def legacy_declared_thresholds_applied():
    corpus = cases()
    reports = arm_reports(corpus)
    full = reports["full"][0]
    schedule = [
        {"ordinal": index + 1, "case": run["case"],
         "repetition": index % 3 + 1}
        for index, run in enumerate(full["runs"])
    ]
    normalized_runs = [
        {**run, "schedule_ordinal": item["ordinal"],
         "repetition": item["repetition"]}
        for item, run in zip(schedule, full["runs"])
    ]
    integrity_args = (
        schedule, normalized_runs, "same", "same", "same", "same", "same", "same",
    )
    integrity_status, integrity_reasons = RUNNER.classify_status(
        full["primary_metrics"], full["secondary_metrics"], *integrity_args,
        thresholds={}, protocol_id=PROTOCOL["protocol_id"],
    )
    assert integrity_status == "PASS"
    assert [reason["code"] for reason in integrity_reasons] == [
        "specificity_integrity_checks_met"
    ]
    status, reasons = RUNNER.classify_specificity_status(
        full["primary_metrics"], full["secondary_metrics"], PROTOCOL,
        integrity_args, {},
    )
    assert status == "PASS"
    assert [reason["code"] for reason in reasons] == [
        "all_specificity_absolute_metrics_met"
    ]
    result = COMPARATOR.decide_specificity_matrix(reports, corpus, PROTOCOL)
    assert result["status"] == "PASS"
    changed = copy.deepcopy(PROTOCOL)
    changed["decision"]["full_arm_absolute_thresholds"]["per_case_specificity_min"] = 1.01
    failed = COMPARATOR.decide_specificity_matrix(reports, corpus, changed)
    assert failed["status"] == "FAIL"
    assert any(row["metric"] == "per_case_specificity_min"
               for row in failed["status_reasons"][0]["failed_checks"])


def legacy_bootstrap_resamples_cases_not_repetitions():
    corpus = cases()
    protocol = copy.deepcopy(PROTOCOL)
    protocol["arm_comparison"]["uncertainty"]["iterations"] = 2
    calls = []

    class RecordingRandom:
        def __init__(self, _seed):
            pass

        def choices(self, population, k):
            calls.append((tuple(population), k))
            return list(population)

    with mock.patch.object(COMPARATOR.random, "Random", RecordingRandom):
        COMPARATOR.paired_specificity_bootstrap(arm_reports(corpus), corpus, protocol)
    assert len(calls) == 4
    assert all(k == 12 and len(population) == 12 for population, k in calls)
    assert all(not any("repetition" in item for item in population)
               for population, _ in calls)


def assert_refused(command):
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 2, result.stderr
    assert "reviewer-specificity-v1 was superseded before run" in result.stderr
    assert "use reviewer-specificity-v3" in result.stderr


def test_runner_and_comparator_refuse_superseded_protocol():
    assert_refused([sys.executable, str(RUNNER_PATH), "--protocol", str(PROTOCOL_PATH)])
    assert_refused([sys.executable, str(COMPARATOR_PATH), str(ROOT / "missing-report.json"),
                    "--cases", str(ROOT / "scripts/evals/reviewer-holdout-v5.json"),
                    "--protocol", str(PROTOCOL_PATH)])


def test_protocol_is_byte_preserved_at_recorded_digest():
    assert hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest() == RECORDED_PROTOCOL_SHA256


def test_supersession_is_recorded_for_readers():
    supersedes = json.loads(SUCCESSOR_PATH.read_text())["supersedes"]
    assert supersedes["protocol_id"] == "reviewer-specificity-v1"
    assert supersedes["disposition"] == "SUPERSEDED_BEFORE_RUN"
    assert (supersedes["model_calls"], supersedes["corpus_cases_created"], supersedes["results"]) == (0, 0, 0)
    assert "v1 remains byte-preserved" in supersedes["reason"]
    assert "FROZEN / SUPERSEDED_BEFORE_RUN" in README_PATH.read_text()
    assert "preserved byte-for-byte but must not be run" in README_PATH.read_text()
    assert "records v1 as `SUPERSEDED_BEFORE_RUN`" in SUCCESSOR_README_PATH.read_text()


def main():
    tests = [test_runner_and_comparator_refuse_superseded_protocol,
             test_protocol_is_byte_preserved_at_recorded_digest,
             test_supersession_is_recorded_for_readers]
    for test in tests:
        test()
    print(f"reviewer-specificity-v1: {len(tests)} supersession tests passed")


if __name__ == "__main__":
    main()

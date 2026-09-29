#!/usr/bin/env python3
"""Exercise reviewer-specificity-v2 adjudication-ledger fail-closed branches."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v2.json"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
SUCCESSOR_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v3.json"
README_PATH = ROOT / "benchmarks/reviewer-specificity-v2/README.md"
SUCCESSOR_README_PATH = ROOT / "benchmarks/reviewer-specificity-v3/README.md"
RECORDED_PROTOCOL_SHA256 = "68a29eea11e7bd0aa4ca2a815e59ecd8b6b391119c7992567955bb32cefc1c02"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_module("specificity_v2_runner", RUNNER_PATH)
PROTOCOL = RUNNER.load_protocol(PROTOCOL_PATH)


def fixture(root: Path):
    source = root / "case-01.ts"
    source.write_text("test('clean', async () => { expect(true).toBe(true); });\n")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    provenance = {
        "repository_identity": "example/project",
        "repository_url": "https://github.com/example/project",
        "full_commit_sha": "a" * 40,
        "default_branch_at_snapshot": "main",
        "repository_rank_and_framework_query": {
            "framework": "playwright", "query": "@playwright/test", "rank": 1,
        },
        "candidate_ordinal": 1,
        "source_paths": ["spec.ts"],
        "immutable_blob_urls": [
            "https://github.com/example/project/blob/" + "a" * 40 + "/spec.ts"
        ],
        "source_file_sha256_values": {"spec.ts": source_sha256},
        "retrieved_at": "2026-09-21T00:00:00Z",
        "lineage_cluster": "example-project-clean-spec",
        "transformations_or_redactions": [],
        "license_spdx_identifier": "MIT",
        "license_file_path": "LICENSE",
        "license_blob_url": (
            "https://github.com/example/project/blob/" + "a" * 40 + "/LICENSE"
        ),
        "license_file_sha256": "b" * 64,
        "redistribution_basis": "MIT licence permits redistribution.",
    }
    case = {
        "id": "case-01", "split": "holdout", "framework": "playwright",
        "source_files": [{"source": source.name, "path": "spec.ts"}],
        "labels": [{
            "finding_id": "guard-01", "kind": "fp_guard", "pattern_id": "#1",
            "severity": "P0", "file": "spec.ts", "line": 1,
            "source_line": "test('clean', async () => { expect(true).toBe(true); });",
        }],
        "provenance": provenance,
    }
    cases_path = root / "cases.json"
    cases_path.write_text("{}\n")
    case_sha256 = RUNNER.specificity_case_sha256(case, cases_path)

    def adjudication_pass(model):
        return {
            "adjudicator": {
                "runner": "claude", "model_family": "claude",
                "model_identifier": model, "model_version": model + "-20260921",
                "runner_version": "Claude Code 2.1.300",
            },
            "prompt_sha256": PROTOCOL["adjudication"]["prompt_sha256"],
            "case_sha256": case_sha256,
            "verdict": "clean", "proposed_findings": [],
            "pattern_coverage": [{
                "pattern_id": pattern_id,
                "rationale": f"{pattern_id} is absent in the cited full-file context.",
                "citations": [{"file": "spec.ts", "line": 1}],
            } for pattern_id in PROTOCOL["adjudication"]["required_pattern_ids"]],
            "rationale": "Reviewed the complete case against all 24 patterns; no finding.",
            "timestamp": "2026-09-21T00:01:00Z", "fresh_session": True,
            "input_exclusions_attested": {
                "other_adjudicator_verdict": False,
                "scanner_candidate_list_rationale": False,
                "treatment_output": False,
                "prior_session_context": False,
            },
        }

    ledger = {
        "schema_version": 1,
        "ledger_id": PROTOCOL["adjudication"]["ledger"]["ledger_id"],
        "protocol_id": PROTOCOL["protocol_id"],
        "pattern_reference_sha256": PROTOCOL["adjudication"]["pattern_reference_sha256"],
        "prompt_sha256": PROTOCOL["adjudication"]["prompt_sha256"],
        "candidates": [{
            "case_id": case["id"], "disposition": "admitted", "discard_reason": None,
            "case_sha256": case_sha256, "provenance": provenance,
            "passes": [adjudication_pass("claude-opus-5"), adjudication_pass("claude-fable-5")],
        }],
    }
    return cases_path, [case], ledger


def write_ledger(root: Path, ledger: dict) -> Path:
    path = root / "ledger.json"
    path.write_text(json.dumps(ledger))
    return path


def expect_failure(fragment: str, action) -> None:
    try:
        action()
    except ValueError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected failure containing {fragment!r}")


def validate(cases_path, cases, ledger_path):
    return RUNNER.validate_specificity_adjudication_ledger(
        cases, cases_path, PROTOCOL, ledger_path,
    )


def legacy_valid_ledger_accepted():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, ledger = fixture(root)
        RUNNER.validate_specificity_cases(cases, "synthetic", PROTOCOL, cases_path)
        assert validate(cases_path, cases, write_ledger(root, ledger)) == ledger


def legacy_missing_ledger_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, _ = fixture(root)
        expect_failure("adjudication ledger is missing", lambda: validate(
            cases_path, cases, root / "missing.json"
        ))


def legacy_missing_adjudicator_identity_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, ledger = fixture(root)
        del ledger["candidates"][0]["passes"][0]["adjudicator"]["model_version"]
        expect_failure("missing adjudicator identity", lambda: validate(
            cases_path, cases, write_ledger(root, ledger)
        ))


def legacy_case_admitted_on_one_pass_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, ledger = fixture(root)
        ledger["candidates"][0]["passes"].pop()
        expect_failure("exactly two adjudication passes", lambda: validate(
            cases_path, cases, write_ledger(root, ledger)
        ))


def legacy_evaluated_family_adjudicator_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, ledger = fixture(root)
        identity = ledger["candidates"][0]["passes"][0]["adjudicator"]
        identity.update({"runner": "codex", "model_family": "codex",
                         "model_identifier": "gpt-5.6-sol"})
        expect_failure("different model family", lambda: validate(
            cases_path, cases, write_ledger(root, ledger)
        ))


def legacy_case_digest_mismatch_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, ledger = fixture(root)
        stale = "0" * 64
        ledger["candidates"][0]["case_sha256"] = stale
        for adjudication_pass in ledger["candidates"][0]["passes"]:
            adjudication_pass["case_sha256"] = stale
        expect_failure("digest does not match its ledger entry", lambda: validate(
            cases_path, cases, write_ledger(root, ledger)
        ))


def assert_refused(command):
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 2, result.stderr
    assert "reviewer-specificity-v2 was superseded before run" in result.stderr
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
    assert supersedes["protocol_id"] == "reviewer-specificity-v2"
    assert supersedes["disposition"] == "SUPERSEDED_BEFORE_RUN"
    assert (supersedes["model_calls"], supersedes["corpus_cases_created"], supersedes["results"]) == (0, 0, 0)
    assert "v2 remains byte-preserved" in supersedes["reason"]
    assert "FROZEN / SUPERSEDED_BEFORE_RUN" in README_PATH.read_text()
    assert "runner and comparator refuse new v1 or v2 work" in README_PATH.read_text()
    assert "V3 supersedes [reviewer specificity v2]" in SUCCESSOR_README_PATH.read_text()
    assert "V2 remains byte-preserved" in SUCCESSOR_README_PATH.read_text()


def main():
    tests = [
        test_runner_and_comparator_refuse_superseded_protocol,
        test_protocol_is_byte_preserved_at_recorded_digest,
        test_supersession_is_recorded_for_readers,
    ]
    for test in tests:
        test()
    print(f"reviewer-specificity-v2: {len(tests)} supersession tests passed")


if __name__ == "__main__":
    main()

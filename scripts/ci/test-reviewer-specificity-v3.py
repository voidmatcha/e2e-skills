#!/usr/bin/env python3
"""Exercise reviewer-specificity-v3 enumeration and fail-closed branches."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v3.json"
V2_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v2.json"
CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v5.json"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_module("specificity_v3_runner", RUNNER_PATH)
COMPARATOR = load_module("specificity_v3_comparator", COMPARATOR_PATH)
PROTOCOL = RUNNER.load_protocol(PROTOCOL_PATH)
V2_PROTOCOL = RUNNER.load_protocol(V2_PROTOCOL_PATH)
# Ledger fixtures exercise today's validator, not a replay of the frozen study.
# Keep PROTOCOL intact for the historical schema/comparison tests below.
LEDGER_PROTOCOL = copy.deepcopy(PROTOCOL)
PATTERN_SHA256 = RUNNER.sha256_file(
    ROOT / "skills/e2e-reviewer/references/pattern-reference.md")
LEDGER_PROTOCOL["adjudication"]["pattern_reference_sha256"] = PATTERN_SHA256
LEDGER_PROTOCOL["corpus"]["frozen_adjudication_inputs"]["pattern_reference_sha256"] = PATTERN_SHA256


def metric_cases(count=24, framework="playwright"):
    return [{
        "id": f"case-{index:02d}", "framework": framework, "split": "holdout",
        "source_files": [{"source": "unused", "path": "spec.ts"}],
        "labels": [],
    } for index in range(count)]


def finding(line=2):
    return {"pattern_id": "#1", "severity": "P0", "file": "spec.ts", "line": line}


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
            "framework": "playwright",
            "query": "language:TypeScript pushed:>=2025-09-21 size:>=1000",
            "rank": 1,
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
        "pattern_reference_sha256": LEDGER_PROTOCOL["adjudication"]["pattern_reference_sha256"],
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
        cases, cases_path, LEDGER_PROTOCOL, ledger_path,
    )


def report(profile, cases, finding_repetitions=()):
    runs = []
    for case in cases:
        for repetition in range(1, 4):
            findings = [finding()] if repetition in finding_repetitions else []
            runs.append({"case": case["id"], "findings": findings,
                         "score": {"tp": 0, "fp": len(findings), "fn": 0}})
    primary, secondary = RUNNER.specificity_metrics(cases, runs, PROTOCOL)
    return {"prompt_profile": profile, "runner": "codex", "model": "gpt-5.6-sol",
            "protocol_id": PROTOCOL["protocol_id"], "status": "PASS", "complete": True,
            "execution_complete": True, "primary_metrics": primary,
            "secondary_metrics": secondary, "runs": runs}


def arm_reports(cases):
    return {"full": [report("full", cases)],
            "catalog-only": [report("catalog-only", cases, {1, 2, 3})],
            "no-skill": [report("no-skill", cases, {1, 2, 3})]}


def provenance_report(profile, started):
    value = report(profile, metric_cases())
    value.update({
        "skill_sha256": "a", "corpus_sha256": "b", "protocol_sha256": "c",
        "schedule_sha256": "d", "repetitions": 3, "evaluator_sha256": "e",
        "git_revision": "revision", "git_dirty": False, "git_dirty_sha256": "f",
        "source_read_isolation": "prompt-complete-zero-tools",
        "workspace_integrity": "pre-post-sha256", "input_snapshot": "copy-once-temp",
        "model_tool_surface": "none", "evidence_scope": "development",
        "runner_identity": "codex-cli 0.154.0", "runner_executable": "/codex",
        "reasoning_effort": None, "started_at": started,
        "created_at": started.replace("00Z", "01Z"),
        "prompt_set_sha256": {"full": "1", "catalog-only": "2", "no-skill": "3"}[profile],
    })
    return value


def test_valid_ledger_accepted():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, ledger = fixture(root)
        RUNNER.validate_specificity_cases(cases, "synthetic", PROTOCOL, cases_path)
        assert validate(cases_path, cases, write_ledger(root, ledger)) == ledger


def test_ledger_rejects_changed_pattern_reference():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, ledger = fixture(root)
        skill = root / "skill"
        (skill / "references").mkdir(parents=True)
        (skill / "references/pattern-reference.md").write_text("Changed fixture.\n")
        ledger_path = write_ledger(root, ledger)
        expect_failure("frozen pattern reference digest does not match", lambda:
            RUNNER.validate_specificity_adjudication_ledger(
                cases, cases_path, LEDGER_PROTOCOL, ledger_path, skill_dir=skill))


def test_majority_boundary():
    cases = metric_cases(2)
    runs = []
    for case, dirty in zip(cases, ({3}, {2, 3})):
        for repetition in range(1, 4):
            findings = [finding()] if repetition in dirty else []
            runs.append({"case": case["id"], "findings": findings,
                         "score": {"tp": 0, "fp": len(findings), "fn": 0}})
    primary, _ = RUNNER.specificity_metrics(cases, runs, PROTOCOL)
    rows = primary["whole_case_specificity"]["by_case"]
    assert rows["case-00"]["stably_clean"] is True
    assert rows["case-01"]["stably_clean"] is False
    assert primary["whole_case_specificity"]["value"] == 0.5
    assert "clean_case_specificity" not in primary


def test_specificity_inputs_reject_findings_and_missing_sources():
    with tempfile.TemporaryDirectory() as temp:
        cases_path, cases, _ = fixture(Path(temp))
        cases[0]["labels"][0]["kind"] = "finding"
        expect_failure("must contain only fp_guard labels", lambda: RUNNER.validate_specificity_cases(
            cases, "synthetic", PROTOCOL, cases_path
        ))
    with tempfile.TemporaryDirectory() as temp:
        cases_path, cases, _ = fixture(Path(temp))
        cases[0]["source_files"] = []
        expect_failure("needs source_files", lambda: RUNNER.validate_specificity_cases(
            cases, "synthetic", PROTOCOL, cases_path
        ))


def test_arm_provenance_disagreement_rejected():
    reports = [provenance_report("full", "2026-08-01T00:00:00Z"),
               provenance_report("catalog-only", "2026-08-01T00:01:00Z"),
               provenance_report("no-skill", "2026-08-01T00:02:00Z")]
    reports[1]["git_dirty"] = True
    with mock.patch.object(COMPARATOR, "recompute_report", side_effect=lambda item, *_a, **_k: item):
        result = COMPARATOR.compare_arm_reports(reports, metric_cases(), "b", PROTOCOL, "c")
    assert result["status"] == "INCONCLUSIVE"
    assert any(reason.get("code") == "arm_provenance_mismatch"
               and reason.get("field") == "git_dirty" for reason in result["status_reasons"])


def test_declared_thresholds_applied():
    cases = metric_cases()
    reports = arm_reports(cases)
    full = reports["full"][0]
    schedule = [{"ordinal": index + 1, "case": run["case"], "repetition": index % 3 + 1}
                for index, run in enumerate(full["runs"])]
    normalized_runs = [{**run, "schedule_ordinal": item["ordinal"],
                        "repetition": item["repetition"]}
                       for item, run in zip(schedule, full["runs"])]
    integrity_args = (schedule, normalized_runs, "same", "same", "same", "same",
                      "same", "same")
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
    assert COMPARATOR.decide_specificity_matrix(reports, cases, PROTOCOL)["status"] == "PASS"
    changed = copy.deepcopy(PROTOCOL)
    changed["decision"]["full_arm_absolute_thresholds"]["per_case_specificity_min"] = 1.01
    failed = COMPARATOR.decide_specificity_matrix(reports, cases, changed)
    assert failed["status"] == "FAIL"
    assert any(row["metric"] == "per_case_specificity_min"
               for row in failed["status_reasons"][0]["failed_checks"])


def test_v3_retains_evaluation_contract_but_amends_population_and_allocation():
    assert PROTOCOL["protocol_id"] == "reviewer-specificity-v3"
    for key in (
        "schema_version", "status", "visibility", "purpose", "clean_verification",
        "stability", "execution_identity", "prompt_arms", "host_matrix", "metrics",
    ):
        assert PROTOCOL[key] == V2_PROTOCOL[key], key
    assert PROTOCOL["decision"]["full_arm_absolute_thresholds"] == V2_PROTOCOL["decision"]["full_arm_absolute_thresholds"]
    assert PROTOCOL["decision"]["full_vs_each_control_thresholds"] == V2_PROTOCOL["decision"]["full_vs_each_control_thresholds"]
    assert PROTOCOL["decision"]["threshold_rationale"] == V2_PROTOCOL["decision"]["threshold_rationale"]
    for key in (
        "case_count_target", "case_count_minimum", "labels", "case_boundary",
        "cases_per_source_repository_max", "deduplication_unit",
        "required_case_provenance_fields", "frozen_adjudication_inputs",
        "case_provenance_storage", "case_provenance_schema",
    ):
        assert PROTOCOL["corpus"][key] == V2_PROTOCOL["corpus"][key], key
    v2_adjudication = json.loads(json.dumps(V2_PROTOCOL["adjudication"]))
    v3_adjudication = json.loads(json.dumps(PROTOCOL["adjudication"]))
    for value in (v2_adjudication, v3_adjudication):
        value["ledger"].pop("path")
        value["ledger"].pop("ledger_id")
    assert v3_adjudication == v2_adjudication
    allocation = PROTOCOL["corpus"]["framework_allocation"]
    assert allocation["cypress_floor"] == 1
    assert allocation["cypress_specific_metrics_minimum_cases"] == 8
    assert "Playwright-only" in allocation["if_floor_unmet"]
    lookalikes = PROTOCOL["corpus"]["source_selection"]["lookalike_allocation"]
    assert "One case for each of the 24" in lookalikes["minimum_24_cases"]
    assert "Two cases for each of the 24" in lookalikes["target_48_cases"]
    uncertainty = PROTOCOL["arm_comparison"]["uncertainty"]
    assert uncertainty["method"] == "paired-case-bootstrap"
    assert uncertainty["strata"] == ["all-clean-cases"]


def test_repository_enumeration_is_frozen_and_auditable():
    selection = PROTOCOL["corpus"]["source_selection"]
    enumeration = selection["repository_enumeration"]
    neutral_queries = [
        "language:TypeScript pushed:>=2025-09-21 size:>=1000",
        "language:JavaScript pushed:>=2025-09-21 size:>=1000",
    ]
    assert enumeration["queries"] == {
        "playwright": neutral_queries,
        "cypress": neutral_queries,
    }
    assert all(
        framework not in query.lower()
        for queries in enumeration["queries"].values()
        for framework in ("playwright", "cypress")
        for query in queries
    )
    assert (enumeration["sort"], enumeration["order"]) == ("stars", "desc")
    assert enumeration["per_page"] == 100
    assert enumeration["maximum_pages_per_query"] == 10
    assert enumeration["maximum_pages_per_framework"] == 20
    assert enumeration["maximum_repositories_per_query"] == 1000
    assert enumeration["maximum_repositories_per_framework"] == 2000
    assert enumeration["repository_walk"]["records_every_returned_repository"] is True
    assert enumeration["repository_walk"]["records_skips_with_reason"] is True
    for phrase in (
        "not all public repositories", "primary language", "no push on or after",
        "smaller than 1,000 KiB", "root default-branch package.json",
    ):
        assert phrase in selection["population"]
    assert "deliberately keyword-free" in enumeration["query_rationale"]
    assert "lower framework-dependency hit rate" in enumeration["query_rationale"]
    assert "3 Cypress declarations across 160 repositories" in enumeration["page_budget_rationale"]
    measurement = selection["framework_population_measurement"]
    assert measurement["measured_on"] == "2026-09-21"
    assert measurement["totals"] == {
        "repositories": 160,
        "playwright_declarations": 31,
        "cypress_declarations": 3,
    }
    assert len(measurement["strata"]) == 4
    assert all(row["repositories"] == 40 for row in measurement["strata"])
    assert "nested monorepo" in measurement["manifest_scope"]
    context = selection["unverified_ecosystem_context"]
    assert context["status"].startswith("not tested by this project")
    assert len(context["items"]) == 4
    assert "specific repository" in context["non_attribution_rule"]


def test_bootstrap_resamples_cases_not_repetitions_with_no_cypress_cases():
    cases = metric_cases()
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
        result = COMPARATOR.paired_specificity_bootstrap(arm_reports(cases), cases, protocol)
    case_ids = tuple(case["id"] for case in cases)
    assert calls == [(case_ids, len(case_ids)), (case_ids, len(case_ids))]
    assert {case["framework"] for case in cases} == {"playwright"}
    assert result["point_metrics"]["full"]["per_case_specificity"] == 1.0
    assert result["intervals"]["catalog-only"]["per_case_specificity"]["strata"] == [
        "all-clean-cases"
    ]


def legacy_v1_and_v2_refused_by_runner_and_comparator():
    for version in (1, 2):
        protocol = ROOT / f"scripts/evals/reviewer-specificity-protocol-v{version}.json"
        runner = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--protocol", str(protocol)],
            cwd=ROOT, text=True, capture_output=True,
        )
        assert runner.returncode == 2, runner.stderr
        assert f"reviewer-specificity-v{version} was superseded before run" in runner.stderr
        assert "use reviewer-specificity-v3" in runner.stderr
        comparator = subprocess.run(
            [
                sys.executable, str(COMPARATOR_PATH), str(ROOT / "missing-report.json"),
                "--cases", str(CASES_PATH), "--protocol", str(protocol),
            ],
            cwd=ROOT, text=True, capture_output=True,
        )
        assert comparator.returncode == 2, comparator.stderr
        assert f"reviewer-specificity-v{version} was superseded before run" in comparator.stderr
        assert "use reviewer-specificity-v3" in comparator.stderr


def test_missing_ledger_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, _ = fixture(root)
        expect_failure("adjudication ledger is missing", lambda: validate(
            cases_path, cases, root / "missing.json"
        ))


def test_missing_repository_walk_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        expect_failure(
            "repository walk is missing",
            lambda: RUNNER.validate_specificity_repository_walk(
                PROTOCOL, Path(temp) / "missing.json"
            ),
        )


def full_repository_walk_fixture() -> dict:
    snapshots = []
    repositories = []
    next_id = 1
    for framework in ("playwright", "cypress"):
        rank = 1
        for query in PROTOCOL["corpus"]["source_selection"]["repository_enumeration"][
                "queries"][framework]:
            pages = []
            for page_number in range(1, 11):
                ids = list(range(next_id, next_id + 100))
                next_id += 100
                pages.append({
                    "page": page_number,
                    "request_url": f"https://api.github.com/search/repositories?page={page_number}",
                    "response_status": 200,
                    "retrieved_at": "2026-09-21T00:00:00Z",
                    "reported_total_count": 2000,
                    "incomplete_results": False,
                    "response_path": f"raw/search/{framework}/page-{page_number:02d}.json",
                    "response_sha256": "a" * 64,
                    "returned_repository_ids": ids,
                })
                for repository_id in ids:
                    repositories.append({
                        "framework": framework,
                        "repository_rank": rank,
                        "repository_id": repository_id,
                        "repository_identity": f"owner-{framework}/repository-{rank:04d}",
                        "search_snapshot_stars": 2001 - rank,
                        "full_commit_sha": f"{repository_id:040x}",
                        "verification_retrieved_at": "2026-09-21T00:00:00Z",
                        "verification_status": "eligible",
                        "skip_reason": None,
                    })
                    rank += 1
            snapshots.append({
                "framework": framework,
                "query": query,
                "sort": "stars",
                "order": "desc",
                "per_page": 100,
                "maximum_pages": 10,
                "pages": pages,
            })
    return {
        "schema_version": 1,
        "protocol_id": "reviewer-specificity-v3",
        "query_snapshots": snapshots,
        "repositories": repositories,
    }


def test_full_walk_uses_documented_artifact_limit() -> None:
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "repository-walk.json"
        path.write_text(json.dumps(full_repository_walk_fixture(), separators=(",", ":")) + "\n")
        assert 1_048_576 < path.stat().st_size < PROTOCOL["corpus"]["source_selection"][
            "repository_enumeration"]["repository_walk"]["maximum_file_bytes"]
        expect_failure("JSON file exceeds 1048576 byte limit", lambda: RUNNER.load_strict(path))
        walk = RUNNER.validate_specificity_repository_walk(PROTOCOL, path)
        assert len(walk["repositories"]) == 4000
        assert [row["verification_status"] for row in walk["repositories"]] == [
            "eligible"
        ] * 4000


def test_case_query_outside_frozen_enumeration_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, _ = fixture(root)
        cases[0]["provenance"]["repository_rank_and_framework_query"]["query"] = (
            "playwright in:name,description,readme"
        )
        expect_failure(
            "invalid repository rank/query provenance",
            lambda: RUNNER.validate_specificity_cases(
                cases, "synthetic", PROTOCOL, cases_path
            ),
        )


def test_missing_adjudicator_identity_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, ledger = fixture(root)
        del ledger["candidates"][0]["passes"][0]["adjudicator"]["model_version"]
        expect_failure("missing adjudicator identity", lambda: validate(
            cases_path, cases, write_ledger(root, ledger)
        ))


def test_case_admitted_on_one_pass_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, ledger = fixture(root)
        ledger["candidates"][0]["passes"].pop()
        expect_failure("exactly two adjudication passes", lambda: validate(
            cases_path, cases, write_ledger(root, ledger)
        ))


def test_evaluated_family_adjudicator_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cases_path, cases, ledger = fixture(root)
        identity = ledger["candidates"][0]["passes"][0]["adjudicator"]
        identity.update({"runner": "codex", "model_family": "codex",
                         "model_identifier": "gpt-5.6-sol"})
        expect_failure("different model family", lambda: validate(
            cases_path, cases, write_ledger(root, ledger)
        ))


def test_case_digest_mismatch_fails_closed():
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


def main():
    tests = [
        test_valid_ledger_accepted,
        test_ledger_rejects_changed_pattern_reference,
        test_majority_boundary,
        test_specificity_inputs_reject_findings_and_missing_sources,
        test_arm_provenance_disagreement_rejected,
        test_declared_thresholds_applied,
        test_v3_retains_evaluation_contract_but_amends_population_and_allocation,
        test_repository_enumeration_is_frozen_and_auditable,
        test_bootstrap_resamples_cases_not_repetitions_with_no_cypress_cases,
        test_missing_ledger_fails_closed,
        test_missing_repository_walk_fails_closed,
        test_full_walk_uses_documented_artifact_limit,
        test_case_query_outside_frozen_enumeration_fails_closed,
        test_missing_adjudicator_identity_fails_closed,
        test_case_admitted_on_one_pass_fails_closed,
        test_evaluated_family_adjudicator_fails_closed,
        test_case_digest_mismatch_fails_closed,
    ]
    for test in tests:
        test()
    print(f"reviewer-specificity-v3: {len(tests)} synthetic tests passed")


if __name__ == "__main__":
    main()

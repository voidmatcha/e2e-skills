#!/usr/bin/env python3
"""Validate exact fixture-mutant provenance for fault-causal benchmark v3."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "scripts/evals/reviewer-fault-causal-v3.json"
PROTOCOL_PATH = (
    ROOT / "scripts/evals/reviewer-validation-protocol-fault-causal-v3.json"
)
LINKAGE_PATH = ROOT / "scripts/evals/reviewer-fault-causal-v3-linkage.json"
OPERATORS_PATH = ROOT / "scripts/evals/run-fixture-faults.py"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
ARTIFACT_ROOT = ROOT / "scripts/evals/files/reviewer-fault-causal-v3"

EXPECTED_CORPUS_SHA256 = (
    "8c96f6a4a93d6ad7dffc277188603aecae71f9602f2461a421b224b25abb4e1e"
)
EXPECTED_PROTOCOL_SHA256 = (
    "4254b10ed53a2d5a87210c035ab629ac4e5ea9cf4b3a776d9bc2eaa556fb80ce"
)
EXPECTED_LINKAGE_SHA256 = (
    "ab7f4c31eea9eefd48fb411e6eb02017fb0996c29cab61b4a64390f4de734e3b"
)
EXPECTED_OPERATOR_SOURCE_SHA256 = (
    "374273b29ac89c33a55cc56b3ed3d017404049a46921abf1a8c7baaa1ee083fa"
)
EXPECTED_OPERATORS = {
    "playwright-error-swallow": ("playwright", "#3", "P0"),
    "playwright-locator-truthiness": ("playwright", "#4f", "P0"),
    "playwright-conditional-assertion": ("playwright", "#5a", "P0"),
    "playwright-discarded-boolean": ("playwright", "#8b", "P0"),
    "playwright-aria-snapshot-name": ("playwright", "#4j", "P1"),
    "playwright-missing-auth": ("playwright", "#12", "P0"),
    "playwright-optimistic-call-proof": ("playwright", "#22", "P1"),
    "cypress-missing-then": ("cypress", "#2", "P0"),
    "cypress-assigned-chainable": ("cypress", "#10e", "P1"),
    "cypress-uncaught-exception": ("cypress", "#3b", "P0"),
    "cypress-focused-test-leak": ("cypress", "#7", "P0"),
    "cypress-fixture-render-guard": ("cypress", "#23", "P2"),
}
EXPECTED_OPERATOR_IDS = set(EXPECTED_OPERATORS)
ANSWER_LEADING_INPUT = re.compile(
    r"\bMutant\b|trusts optimistic|removes (?:the )?postcondition|"
    r"answer[- ](?:hint|leading)|known (?:fault|smell|pattern)",
    re.IGNORECASE,
)
ROOT_KEYS = {
    "schema_version",
    "corpus_visibility",
    "intended_use",
    "contamination_risk",
    "cases",
}
CASE_KEYS = {"id", "split", "framework", "source_files", "labels"}
SOURCE_KEYS = {"source", "path"}
LABEL_KEYS = {
    "finding_id",
    "kind",
    "pattern_id",
    "severity",
    "file",
    "line",
    "source_line",
}
LINKAGE_KEYS = {
    "schema_version",
    "benchmark_id",
    "evidence_scope",
    "operator_source",
    "operator_source_sha256",
    "derivation",
    "claims_excluded",
    "links",
}
LINK_KEYS = {
    "operator_id",
    "pattern_id",
    "framework",
    "fixture_spec",
    "benchmark_source",
    "clean_case_id",
    "mutant_case_id",
    "clean_spec_sha256",
    "operator_mutant_sha256",
    "benchmark_input_sha256",
    "marker_sha256",
    "replacement_sha256",
    "transformation_sha256",
    "operator_transformed_span",
    "marker_occurrences",
    "artifact_relation",
    "answer_hint_contaminated",
    "comment_neutralization",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_strict(path: Path) -> dict:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )
    if not isinstance(value, dict):
        raise AssertionError(f"{path}: root must be an object")
    return value


def require_exact_keys(value: object, expected: set[str], context: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise AssertionError(f"{context}: expected {sorted(expected)}, got {actual}")


def parse_operators() -> dict[str, dict]:
    tree = ast.parse(OPERATORS_PATH.read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "OPERATORS"
            for target in node.targets
        )
    )
    assert isinstance(assignment.value, ast.Tuple)
    result = {}
    for entry in assignment.value.elts:
        assert isinstance(entry, ast.Call)
        assert isinstance(entry.func, ast.Name) and entry.func.id == "Operator"
        fields = {
            keyword.arg: ast.literal_eval(keyword.value)
            for keyword in entry.keywords
            if keyword.arg is not None
        }
        result[fields["id"]] = fields
    return result


def validate_corpus() -> dict[str, dict]:
    assert sha256_file(CASES_PATH) == EXPECTED_CORPUS_SHA256
    corpus = load_strict(CASES_PATH)
    require_exact_keys(corpus, ROOT_KEYS, "corpus")
    assert corpus["schema_version"] == 1
    assert corpus["corpus_visibility"] == "public"
    assert "fixed public-development evidence only" in corpus["intended_use"]
    assert "not sealed generalization" in corpus["intended_use"]
    assert "public and inspectable" in corpus["contamination_risk"].lower()
    assert "independent blind evaluation" in corpus["contamination_risk"]

    cases = corpus["cases"]
    assert isinstance(cases, list) and len(cases) == 24
    by_id = {}
    for case in cases:
        require_exact_keys(case, CASE_KEYS, f"case {case.get('id')}")
        case_id = case["id"]
        assert case_id not in by_id
        by_id[case_id] = case
        assert case["framework"] in {"playwright", "cypress"}
        assert len(case["source_files"]) == 1
        source = case["source_files"][0]
        require_exact_keys(source, SOURCE_KEYS, f"{case_id} source")
        source_name = PurePosixPath(source["source"])
        assert not source_name.is_absolute() and ".." not in source_name.parts
        source_path = CASES_PATH.parent / source_name
        assert source_path.is_file()
        source_text = source_path.read_text(encoding="utf-8")
        assert not ANSWER_LEADING_INPUT.search(source_text), (
            f"{case_id}: staged input contains an answer-leading comment"
        )
        assert len(case["labels"]) == 1
        label = case["labels"][0]
        require_exact_keys(label, LABEL_KEYS, f"{case_id} label")
        assert label["file"] == source["path"]
        lines = source_text.splitlines()
        assert label["source_line"] == lines[label["line"] - 1].strip()
        assert re.fullmatch(r"FCV3-[0-9]{2}-[FG]", label["finding_id"])

        if case_id.endswith("-mutant"):
            assert case["split"] == "public-fault-causal-v3-mutant"
            assert label["kind"] == "finding"
            assert "reviewer-fault-causal-v3" in source["source"]
        elif case_id.endswith("-clean-guard"):
            assert case["split"] == "public-fault-causal-v3-clean-guard"
            assert label["kind"] == "fp_guard"
            assert source["source"].startswith("fixtures/")
            assert "reviewer-fault-causal-v3" not in source["source"]
        else:
            raise AssertionError(f"{case_id}: case must be mutant or clean guard")
    assert sum(case_id.endswith("-mutant") for case_id in by_id) == 12
    assert sum(case_id.endswith("-clean-guard") for case_id in by_id) == 12
    return by_id


def validate_linkage(cases: dict[str, dict], operators: dict[str, dict]) -> None:
    assert sha256_file(LINKAGE_PATH) == EXPECTED_LINKAGE_SHA256
    linkage = load_strict(LINKAGE_PATH)
    require_exact_keys(linkage, LINKAGE_KEYS, "linkage")
    assert linkage["schema_version"] == 1
    assert linkage["benchmark_id"] == "reviewer-fault-causal-v3"
    assert linkage["evidence_scope"] == "public-development-only"
    assert linkage["operator_source"] == OPERATORS_PATH.relative_to(ROOT).as_posix()
    assert linkage["operator_source_sha256"] == EXPECTED_OPERATOR_SOURCE_SHA256
    assert sha256_file(OPERATORS_PATH) == EXPECTED_OPERATOR_SOURCE_SHA256
    assert "exact comment bytes, spans, and hashes" in linkage["derivation"]
    assert "no executable statement changed" in linkage["derivation"]
    assert set(linkage["claims_excluded"]) == {
        "sealed or hidden holdout",
        "unbiased release evidence",
        "generalization beyond these 12 operators",
        "test-generation quality",
    }

    links = linkage["links"]
    assert isinstance(links, list) and len(links) == 12
    assert {link["operator_id"] for link in links} == EXPECTED_OPERATOR_IDS
    accounted_artifacts = set()
    neutralized_ids = set()

    for link in links:
        require_exact_keys(link, LINK_KEYS, f"link {link.get('operator_id')}")
        operator = operators[link["operator_id"]]
        framework, pattern_id, severity = EXPECTED_OPERATORS[link["operator_id"]]
        assert (operator["framework"], operator["pattern_id"]) == (
            framework,
            pattern_id,
        )
        assert (link["framework"], link["pattern_id"]) == (framework, pattern_id)
        assert link["answer_hint_contaminated"] is False

        clean_path = ROOT / link["fixture_spec"]
        benchmark_path = ROOT / link["benchmark_source"]
        assert clean_path == ROOT / "scripts/evals/fixtures" / operator["spec"]
        assert "reviewer-fault-causal-v3" in link["benchmark_source"]
        assert "reviewer-fault-causal-v2" not in link["benchmark_source"]
        clean = clean_path.read_bytes()
        marker = operator["marker"].encode()
        replacement = operator["replacement"].encode()
        assert clean.count(marker) == 1
        start = clean.index(marker)
        derived_mutant = clean[:start] + replacement + clean[start + len(marker) :]
        benchmark_input = benchmark_path.read_bytes()

        assert link["clean_spec_sha256"] == sha256_bytes(clean)
        assert link["operator_mutant_sha256"] == sha256_bytes(derived_mutant)
        assert link["benchmark_input_sha256"] == sha256_bytes(benchmark_input)
        assert link["marker_sha256"] == sha256_bytes(marker)
        assert link["replacement_sha256"] == sha256_bytes(replacement)
        assert link["transformation_sha256"] == sha256_bytes(
            marker + b"\0" + replacement
        )
        assert link["marker_occurrences"] == 1
        assert link["operator_transformed_span"] == {
            "clean_start_byte": start,
            "clean_end_byte": start + len(marker),
            "mutant_end_byte": start + len(replacement),
        }

        mutant_case = cases[link["mutant_case_id"]]
        clean_case = cases[link["clean_case_id"]]
        assert mutant_case["framework"] == framework
        assert clean_case["framework"] == framework
        staged_mutant_path = (
            CASES_PATH.parent / mutant_case["source_files"][0]["source"]
        )
        assert staged_mutant_path.resolve() == benchmark_path.resolve()
        assert staged_mutant_path.read_bytes() == benchmark_input
        assert (
            CASES_PATH.parent / clean_case["source_files"][0]["source"]
        ).read_bytes() == clean
        for case in (mutant_case, clean_case):
            assert case["labels"][0]["pattern_id"] == pattern_id
            assert case["labels"][0]["severity"] == severity
        accounted_artifacts.add(benchmark_path.resolve())

        operator_comment_match = re.search(rb"//\s*Mutant[^\n]*", derived_mutant)
        neutralization = link["comment_neutralization"]
        if operator_comment_match:
            neutralized_ids.add(link["operator_id"])
            require_exact_keys(
                neutralization,
                {
                    "operator_comment",
                    "benchmark_comment",
                    "operator_comment_sha256",
                    "benchmark_comment_sha256",
                    "comment_span",
                    "executable_statements_unchanged",
                },
                f"{link['operator_id']} comment neutralization",
            )
            operator_comment = operator_comment_match.group()
            benchmark_comment = b"// Variant."
            expected_benchmark = (
                derived_mutant[: operator_comment_match.start()]
                + benchmark_comment
                + derived_mutant[operator_comment_match.end() :]
            )
            assert benchmark_input == expected_benchmark
            assert neutralization["operator_comment"].encode() == operator_comment
            assert neutralization["benchmark_comment"].encode() == benchmark_comment
            assert neutralization["operator_comment_sha256"] == sha256_bytes(
                operator_comment
            )
            assert neutralization["benchmark_comment_sha256"] == sha256_bytes(
                benchmark_comment
            )
            assert neutralization["comment_span"] == {
                "operator_start_byte": operator_comment_match.start(),
                "operator_end_byte": operator_comment_match.end(),
                "benchmark_end_byte": (
                    operator_comment_match.start() + len(benchmark_comment)
                ),
            }
            assert neutralization["executable_statements_unchanged"] is True
            assert link["artifact_relation"] == "exact-mutant-comment-neutralization"
        else:
            assert neutralization is None
            assert benchmark_input == derived_mutant
            assert link["artifact_relation"] == "byte-identical-exact-mutant"

    assert neutralized_ids == {
        "playwright-optimistic-call-proof",
        "cypress-missing-then",
    }
    actual_artifacts = {
        path.resolve() for path in ARTIFACT_ROOT.rglob("*") if path.is_file()
    }
    assert actual_artifacts == accounted_artifacts


def validate_protocol(cases: dict[str, dict]) -> None:
    assert sha256_file(PROTOCOL_PATH) == EXPECTED_PROTOCOL_SHA256
    protocol = load_strict(PROTOCOL_PATH)
    require_exact_keys(
        protocol,
        {
            "schema_version",
            "protocol_id",
            "schedule",
            "stability",
            "host_matrix",
            "confidence_intervals",
            "decision",
            "cross_host_decision",
        },
        "protocol",
    )
    assert protocol["schema_version"] == 1
    assert protocol["protocol_id"] == "reviewer-fault-causal-v3"
    assert protocol["schedule"] == {
        "algorithm": "sha256-seeded-sort-v1",
        "seed": 20260802,
        "default_repetitions": 3,
        "release_repetitions": 3,
        "evidence_scope": "public-development",
        "freeze_policy": (
            "Freeze sources, labels, linkage, and protocol before the first "
            "measured run. Any later edit creates a new version."
        ),
    }
    assert len(cases) * protocol["schedule"]["default_repetitions"] == 72
    assert protocol["stability"] == {
        "rule": "strict-majority",
        "minimum_repetitions": 3,
    }
    assert protocol["host_matrix"] == [
        {"runner": "codex", "model": "gpt-5.6-sol"},
        {"runner": "claude", "model": "claude-opus-5"},
        {"runner": "claude", "model": "claude-fable-5"},
    ]
    assert protocol["decision"]["thresholds"] == {
        "stable_precision_min": 0.95,
        "stable_recall_min": 0.9,
        "repeated_precision_min": 0.9,
        "pattern_macro_recall_min": 0.85,
        "case_macro_recall_min": 0.85,
        "framework_macro_recall_min": 0.85,
        "p0_stable_label_recall_min": 0.9,
        "stable_guard_hit_rate_max": 0.05,
    }
    assert "small fixed public development corpus" in protocol["decision"][
        "point_estimate_limits"
    ]
    assert protocol["cross_host_decision"] == {
        "threshold_basis": "point-estimate",
        "requires_each_report_status": "PASS",
        "aggregation_intent": (
            "Compute within-provider-family results first, then give OpenAI "
            "and Anthropic equal top-level weight."
        ),
        "provider_family_balance_required": True,
        "thresholds": {
            "stable_recall_gap_max": 0.1,
            "stable_prediction_jaccard_min": 0.8,
        },
    }
    spec = importlib.util.spec_from_file_location(
        "reviewer_fault_causal_v3_runner",
        RUNNER_PATH,
    )
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert runner.FAULT_CAUSAL_V3_CASES == CASES_PATH
    assert runner.FAULT_CAUSAL_V3_PROTOCOL == PROTOCOL_PATH
    assert runner.load_protocol(PROTOCOL_PATH) == protocol
    assert (
        protocol["protocol_id"]
        not in runner.HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS
    )
    assert protocol["protocol_id"] in runner.PROVIDER_BALANCED_PROTOCOL_IDS
    assert protocol["protocol_id"] in runner.FULL_ONLY_PROTOCOL_IDS
    pinned = runner.PINNED_LIVE_INPUTS[(CASES_PATH, PROTOCOL_PATH)]
    assert pinned == {
        "cases_file_sha256": EXPECTED_CORPUS_SHA256,
        "corpus_sha256": runner.corpus_digest(CASES_PATH, list(cases.values())),
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
    }
    assert "reviewer-fault-causal-v2" in (
        runner.HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS
    )
    unregistered_arm = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--cases",
            str(CASES_PATH),
            "--protocol",
            str(PROTOCOL_PATH),
            "--runner",
            "codex",
            "--arm",
            "no-skill",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    assert unregistered_arm.returncode == 2, unregistered_arm.stdout
    assert "preregisters only the full prompt arm" in unregistered_arm.stdout
    for historical_cases, historical_protocol in (
        (runner.V4_CASES, runner.V4_PROTOCOL),
        (runner.FAULT_CAUSAL_V2_CASES, runner.FAULT_CAUSAL_V2_PROTOCOL),
    ):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--cases",
                str(historical_cases),
                "--protocol",
                str(historical_protocol),
                "--runner",
                "codex",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        assert result.returncode == 2, result.stdout
        assert "frozen historical diagnostic evidence" in result.stdout
        comparison = subprocess.run(
            [
                sys.executable,
                str(COMPARATOR_PATH),
                str(ROOT / "does-not-exist.json"),
                "--cases",
                str(historical_cases),
                "--protocol",
                str(historical_protocol),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        assert comparison.returncode == 2, comparison.stdout
        assert "frozen historical diagnostic evidence" in comparison.stdout


def main() -> None:
    for artifact in (CASES_PATH, PROTOCOL_PATH, LINKAGE_PATH):
        assert "reviewer-fault-causal-v2" not in artifact.read_text(encoding="utf-8")
    operators = parse_operators()
    assert set(operators) == EXPECTED_OPERATOR_IDS
    cases = validate_corpus()
    validate_linkage(cases, operators)
    validate_protocol(cases)
    print(
        "reviewer fault-causal v3: 10 byte-identical mutants, 2 exact "
        "comment-neutralized mutants, 12 separate clean guards, provenance PASS"
    )


if __name__ == "__main__":
    main()

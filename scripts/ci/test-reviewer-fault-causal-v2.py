#!/usr/bin/env python3
"""Validate exact fixture-mutant provenance for fault-causal benchmark v2."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "scripts/evals/reviewer-fault-causal-v2.json"
PROTOCOL_PATH = (
    ROOT / "scripts/evals/reviewer-validation-protocol-fault-causal-v2.json"
)
LINKAGE_PATH = ROOT / "scripts/evals/reviewer-fault-causal-v2-linkage.json"
OPERATORS_PATH = ROOT / "scripts/evals/run-fixture-faults.py"
ARTIFACT_ROOT = ROOT / "scripts/evals/files/reviewer-fault-causal-v2"

EXPECTED_LINKAGE_SHA256 = (
    "f79491007d37690a7c0c95056d3f89439346a7322bdeb04975903543eacad702"
)
EXPECTED_OPERATOR_IDS = {
    "playwright-error-swallow",
    "playwright-locator-truthiness",
    "playwright-conditional-assertion",
    "playwright-discarded-boolean",
    "playwright-aria-snapshot-name",
    "playwright-missing-auth",
    "playwright-optimistic-call-proof",
    "cypress-missing-then",
    "cypress-assigned-chainable",
    "cypress-uncaught-exception",
    "cypress-focused-test-leak",
    "cypress-fixture-render-guard",
}
EXPECTED_SEVERITIES = {
    "#2": "P0",
    "#3": "P0",
    "#3b": "P0",
    "#4f": "P0",
    "#4j": "P1",
    "#5a": "P0",
    "#7": "P0",
    "#8b": "P0",
    "#10e": "P1",
    "#12": "P0",
    "#22": "P1",
    "#23": "P2",
}
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
    "mutant_source",
    "clean_case_id",
    "mutant_case_id",
    "clean_spec_sha256",
    "mutant_spec_sha256",
    "marker_sha256",
    "replacement_sha256",
    "transformation_sha256",
    "transformed_span",
    "marker_occurrences",
    "artifact_relation",
    "answer_hint_contaminated",
    "neutral_ablation",
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
    corpus = load_strict(CASES_PATH)
    require_exact_keys(corpus, ROOT_KEYS, "corpus")
    assert corpus["schema_version"] == 1
    assert corpus["corpus_visibility"] == "public"
    assert "development evidence only" in corpus["intended_use"]
    assert "not sealed generalization" in corpus["intended_use"]
    assert "answer-hint-contaminable" in corpus["contamination_risk"]
    assert "not benchmark inputs" in corpus["contamination_risk"]

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
        assert len(case["labels"]) == 1
        label = case["labels"][0]
        require_exact_keys(label, LABEL_KEYS, f"{case_id} label")
        assert label["file"] == source["path"]
        assert label["severity"] == EXPECTED_SEVERITIES[label["pattern_id"]]
        lines = source_path.read_text(encoding="utf-8").splitlines()
        assert label["source_line"] == lines[label["line"] - 1].strip()

        if case_id.endswith("-mutant"):
            assert case["split"] == "public-fault-causal-v2-mutant"
            assert label["kind"] == "finding"
            assert "reviewer-fault-causal-v2" in source["source"]
        elif case_id.endswith("-clean-guard"):
            assert case["split"] == "public-fault-causal-v2-clean-guard"
            assert label["kind"] == "fp_guard"
            assert source["source"].startswith("fixtures/")
            assert "reviewer-fault-causal-v2" not in source["source"]
        else:
            raise AssertionError(f"{case_id}: case must be mutant or clean guard")
    return by_id


def validate_linkage(cases: dict[str, dict], operators: dict[str, dict]) -> None:
    assert sha256_file(LINKAGE_PATH) == EXPECTED_LINKAGE_SHA256
    linkage = load_strict(LINKAGE_PATH)
    require_exact_keys(linkage, LINKAGE_KEYS, "linkage")
    assert linkage["schema_version"] == 1
    assert linkage["benchmark_id"] == "reviewer-fault-causal-v2"
    assert linkage["evidence_scope"] == "public-development-only"
    assert linkage["operator_source"] == OPERATORS_PATH.relative_to(ROOT).as_posix()
    assert linkage["operator_source_sha256"] == sha256_file(OPERATORS_PATH)
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
    contaminated_ids = set()

    for link in links:
        require_exact_keys(link, LINK_KEYS, f"link {link.get('operator_id')}")
        operator = operators[link["operator_id"]]
        assert link["pattern_id"] == operator["pattern_id"]
        assert link["framework"] == operator["framework"]
        assert link["artifact_relation"] == "byte-identical-exact-mutant"

        clean_path = ROOT / link["fixture_spec"]
        mutant_path = ROOT / link["mutant_source"]
        assert clean_path == ROOT / "scripts/evals/fixtures" / operator["spec"]
        clean = clean_path.read_bytes()
        marker = operator["marker"].encode()
        replacement = operator["replacement"].encode()
        assert clean.count(marker) == 1
        start = clean.index(marker)
        derived_mutant = clean[:start] + replacement + clean[start + len(marker) :]
        actual_mutant = mutant_path.read_bytes()

        assert actual_mutant == derived_mutant
        assert link["clean_spec_sha256"] == sha256_bytes(clean)
        assert link["mutant_spec_sha256"] == sha256_bytes(actual_mutant)
        assert link["marker_sha256"] == sha256_bytes(marker)
        assert link["replacement_sha256"] == sha256_bytes(replacement)
        assert link["transformation_sha256"] == sha256_bytes(
            marker + b"\0" + replacement
        )
        assert link["marker_occurrences"] == 1
        assert link["transformed_span"] == {
            "clean_start_byte": start,
            "clean_end_byte": start + len(marker),
            "mutant_end_byte": start + len(replacement),
        }

        mutant_case = cases[link["mutant_case_id"]]
        clean_case = cases[link["clean_case_id"]]
        assert mutant_case["framework"] == operator["framework"]
        assert clean_case["framework"] == operator["framework"]
        assert (
            CASES_PATH.parent / mutant_case["source_files"][0]["source"]
        ).read_bytes() == derived_mutant
        assert (
            CASES_PATH.parent / clean_case["source_files"][0]["source"]
        ).read_bytes() == clean
        assert mutant_case["labels"][0]["pattern_id"] == operator["pattern_id"]
        assert clean_case["labels"][0]["pattern_id"] == operator["pattern_id"]
        accounted_artifacts.add(mutant_path.resolve())

        contaminated = bool(re.search(r"//\s*Mutant\b", operator["replacement"]))
        assert link["answer_hint_contaminated"] is contaminated
        ablation = link["neutral_ablation"]
        if contaminated:
            contaminated_ids.add(link["operator_id"])
            require_exact_keys(
                ablation,
                {"source", "sha256", "benchmark_input", "neutralization"},
                f"{link['operator_id']} ablation",
            )
            ablation_path = ROOT / ablation["source"]
            expected_ablation = re.sub(
                rb"//\s*Mutant[^\n]*",
                b"// Variant.",
                derived_mutant,
                count=1,
            )
            assert ablation_path.read_bytes() == expected_ablation
            assert ablation["sha256"] == sha256_file(ablation_path)
            assert ablation["benchmark_input"] is False
            assert all(
                source["source"] != ablation["source"]
                for case in cases.values()
                for source in case["source_files"]
            )
            accounted_artifacts.add(ablation_path.resolve())
        else:
            assert ablation is None

    assert contaminated_ids == {
        "playwright-optimistic-call-proof",
        "cypress-missing-then",
    }
    actual_artifacts = {
        path.resolve() for path in ARTIFACT_ROOT.rglob("*") if path.is_file()
    }
    assert actual_artifacts == accounted_artifacts


def validate_protocol(cases: dict[str, dict]) -> None:
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
    assert protocol["protocol_id"] == "reviewer-fault-causal-v2"
    assert protocol["schedule"] == {
        "algorithm": "sha256-seeded-sort-v1",
        "seed": 20260731,
        "default_repetitions": 3,
        "release_repetitions": 3,
    }
    assert len(cases) * protocol["schedule"]["default_repetitions"] == 72
    assert protocol["stability"] == {"rule": "strict-majority"}
    assert len(protocol["host_matrix"]) == 3
    assert protocol["decision"]["thresholds"]["stable_precision_min"] == 0.95
    assert protocol["decision"]["thresholds"]["stable_guard_hit_rate_max"] == 0.05
    assert protocol["cross_host_decision"]["requires_each_report_status"] == "PASS"


def main() -> None:
    operators = parse_operators()
    assert set(operators) == EXPECTED_OPERATOR_IDS
    cases = validate_corpus()
    validate_linkage(cases, operators)
    validate_protocol(cases)
    print(
        "reviewer fault-causal v2: 12 exact mutants, 12 separate clean guards, "
        "2 disclosed neutral ablations, provenance PASS"
    )


if __name__ == "__main__":
    main()

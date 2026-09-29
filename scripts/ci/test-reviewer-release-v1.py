#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Mutation tests for the reviewer release-v1 fail-closed validator."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "evals" / "validate-reviewer-release-v1.py"
PROTOCOL_PATH = ROOT / "scripts" / "evals" / "reviewer-release-v1-protocol.json"
SPEC = importlib.util.spec_from_file_location("reviewer_release_v1_validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_protocol_snapshot_binds_exact_parsed_bytes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "protocol.json"
        original = PROTOCOL_PATH.read_bytes()
        path.write_bytes(original)
        protocol, snapshot_hash = VALIDATOR.load_protocol_snapshot(path)
        assert snapshot_hash == hashlib.sha256(original).hexdigest()
        path.write_bytes(b"{}\n")
        VALIDATOR.validate_protocol(protocol)
        assert snapshot_hash != digest(path)


def ref(path: Path, root: Path) -> dict[str, str]:
    return {"path": path.relative_to(root).as_posix(), "sha256": digest(path)}


def vote(reviewer_id: str, kind: str, taxonomy_id: str | None, severity: str | None, accepted_locations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "reviewer_id": reviewer_id,
        "blinded": True,
        "kind": kind,
        "taxonomy_id": taxonomy_id,
        "severity": severity,
        "accepted_locations": accepted_locations,
        "no_unlisted_scoring_valid_findings": True,
        "recorded_at": "2026-09-01T00:00:00Z",
    }


def make_bundle(root: Path) -> dict[str, Any]:
    taxonomy = list(VALIDATOR.TAXONOMY.items())
    taxonomy_ids = [pattern_id for pattern_id, _severity in taxonomy]
    p0_ids = [pattern_id for pattern_id, severity in taxonomy if severity == "P0"]
    p2_ids = [pattern_id for pattern_id, severity in taxonomy if severity == "P2"]
    positive_patterns = taxonomy_ids * 2 + p0_ids[:4] + p2_ids * 2 + p2_ids[:2]
    assert len(positive_patterns) == 60
    cases: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    adjudications: list[dict[str, Any]] = []
    positive_index = 0
    clean_index = 0
    for index in range(120):
        case_id = f"case-{index + 1:03d}"
        framework = "playwright" if index < 60 else "cypress"
        positive = index % 60 < 30
        kind = "positive" if positive else "clean"
        if positive:
            taxonomy_id = positive_patterns[positive_index]
            severity = VALIDATOR.TAXONOMY[taxonomy_id]
            guard_taxonomy_ids: list[str] = []
            positive_index += 1
        else:
            taxonomy_id, severity = None, None
            guard_taxonomy_ids = [
                taxonomy_ids[clean_index % len(taxonomy_ids)],
                taxonomy_ids[(clean_index + 12) % len(taxonomy_ids)],
            ]
            clean_index += 1
        source_root = root / "sources" / case_id
        source = source_root / "e2e" / "example.spec.ts"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"synthetic source {case_id}\n", encoding="utf-8")
        source_files = [ref(source, root)]
        finding_source = source
        if index == 0:
            helper = source_root / "support" / "helper.ts"
            helper.parent.mkdir(parents=True, exist_ok=True)
            helper.write_text("synthetic helper finding\n", encoding="utf-8")
            source_files.append(ref(helper, root))
            finding_source = helper
        cases.append(
            {
                "case_id": case_id,
                "repo_id": f"repo-{index // 2 + 1:03d}",
                "framework": framework,
                "kind": kind,
                "source_root": source_root.relative_to(root).as_posix(),
                "source_files": source_files,
                "taxonomy_id": taxonomy_id,
                "severity": severity,
                "guard_taxonomy_ids": guard_taxonomy_ids,
            }
        )
        accepted_locations = [{"file": finding_source.relative_to(root).as_posix(), "line": 1}] if positive else []
        labels.append(
            {
                "case_id": case_id,
                "kind": kind,
                "taxonomy_id": taxonomy_id,
                "severity": severity,
                "accepted_locations": accepted_locations,
            }
        )
        first = vote("human-a", kind, taxonomy_id, severity, accepted_locations)
        second = vote("human-b", kind, taxonomy_id, severity, accepted_locations)
        adjudications.append(
            {"case_id": case_id, "reviewer_1": first, "reviewer_2": second, "tie_break": None}
        )

    corpus_path = root / "corpus.json"
    labels_path = root / "labels.json"
    adjudications_path = root / "adjudications.json"
    custody_path = root / "custody.json"
    dump(
        corpus_path,
        {
            "schema_version": 1,
            "protocol_id": "reviewer-release-v1",
            "corpus_id": "external-corpus-001",
            "frozen_at": "2026-09-01T00:00:00Z",
            "cases": cases,
        },
    )
    dump(
        labels_path,
        {"schema_version": 1, "corpus_id": "external-corpus-001", "model_visible": False, "labels": labels},
    )
    dump(
        adjudications_path,
        {
            "schema_version": 1,
            "corpus_id": "external-corpus-001",
            "completed_before_model_run": True,
            "model_outputs_seen": False,
            "records": adjudications,
        },
    )
    dump(
        custody_path,
        {
            "schema_version": 1,
            "corpus_id": "external-corpus-001",
            "sealed_before_model_run": True,
            "model_access": False,
            "custodian": "independent-custodian",
            "events": [
                {
                    "event_id": "freeze-001",
                    "timestamp": "2026-09-01T00:00:00Z",
                    "actor": "independent-custodian",
                    "action": "sealed corpus and oracle",
                    "artifact_sha256": digest(corpus_path),
                }
            ],
        },
    )
    # Fake verifier output tests the preflight interface, not Ed25519 validity.
    attestation = root / "isolation.attestation"
    attestation.write_text("signed-attestation-placeholder\n", encoding="utf-8")
    verifier = root.parent / f"verify-attestation-{root.name}"
    verifier.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' '{{\"verified\":true,\"phase\":\"pre_run\",\"protocol_id\":\"reviewer-release-v1\",\"corpus_id\":\"external-corpus-001\",\"attestation_sha256\":\"{digest(attestation)}\"}}'\n",
        encoding="utf-8",
    )
    verifier.chmod(0o700)
    manifest = {
        "schema_version": 1,
        "protocol_id": "reviewer-release-v1",
        "corpus": ref(corpus_path, root),
        "labels": ref(labels_path, root),
        "adjudications": ref(adjudications_path, root),
        "custody": ref(custody_path, root),
        "isolation": {"pre_run_attestation": ref(attestation, root)},
    }
    dump(root / "bundle.json", manifest)
    return manifest


def expect_error(action: Callable[[], Any], needle: str) -> None:
    try:
        action()
    except VALIDATOR.ValidationError as exc:
        assert needle in str(exc), (needle, str(exc))
    else:
        raise AssertionError(f"expected ValidationError containing {needle!r}")


def mutate_json(path: Path, mutation: Callable[[dict[str, Any]], None]) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutation(value)
    dump(path, value)


def refresh_manifest_ref(root: Path, key: str, path: Path) -> None:
    mutate_json(root / "bundle.json", lambda value: value.__setitem__(key, ref(path, root)))


def bundle_root(directory: str) -> Path:
    root = Path(directory) / "bundle"
    root.mkdir()
    return root


def trusted_verifier(root: Path) -> Path:
    return root.parent / f"verify-attestation-{root.name}"


def test_protocol_only_accepts_pending_contract() -> None:
    VALIDATOR.validate_protocol(VALIDATOR.load_json(PROTOCOL_PATH))
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), "--protocol-only"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "PASS (protocol-only)" in completed.stdout


def test_protocol_rejects_duplicate_keys() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "duplicate.json"
        path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        expect_error(lambda: VALIDATOR.load_json(path), "duplicate JSON object key")


def test_protocol_mutations_fail_closed() -> None:
    protocol = VALIDATOR.load_json(PROTOCOL_PATH)
    mutations = (
        (lambda value: value.__setitem__("unexpected", True), "unknown=['unexpected']"),
        (lambda value: value["corpus"].__setitem__("unique_cases", 119), "expected 120"),
        (lambda value: value["corpus"]["frameworks"]["playwright"].__setitem__("clean", 29), "expected {'positive': 30, 'clean': 30}"),
        (lambda value: value["corpus"]["case_source_limits"].__setitem__("files_max", 1000), "protocol.corpus.case_source_limits"),
        (lambda value: value["execution_identity"].__setitem__("version_policy", "exact"), "expected 'minimum'"),
        (lambda value: value["evaluation_surface"]["initial_model_visible_files"]["full"].append("skills/e2e-reviewer/references/semantic-review.md"), "protocol.evaluation_surface"),
        (lambda value: value["evaluation_surface"].__setitem__("common_taxonomy_index", "none"), "protocol.evaluation_surface"),
        (lambda value: value["evaluation_surface"].__setitem__("common_prompt_template", "Review {{CASE_FILES_JSON}}"), "protocol.evaluation_surface"),
        (lambda value: value["evaluation_surface"].__setitem__("common_taxonomy_index_sha256", "0" * 64), "protocol.evaluation_surface"),
        (lambda value: value["evaluation_surface"].__setitem__("runner_decoding_settings", "custom"), "protocol.evaluation_surface"),
        (lambda value: value["arms"][2].__setitem__("input", "task_prompt_without_skill_or_catalog"), "preregistered treatment"),
        (lambda value: value["evaluation_surface"]["treatment_specific_tools"]["no-skill"].append("run_staged_bundled_scanner"), "protocol.evaluation_surface"),
        (lambda value: value["evaluation_surface"].__setitem__("network_access", True), "protocol.evaluation_surface"),
        (lambda value: value["execution_identity"]["primary"].__setitem__("model", ""), "expected a preregistered"),
        (lambda value: value["schedule"].__setitem__("scheduled_model_calls", 360), "expected 1080"),
        (lambda value: value["schedule"].__setitem__("per_call_wall_timeout_seconds", 601), "protocol.schedule.per_call_wall_timeout_seconds"),
        (lambda value: value["schedule"].__setitem__("attempts_per_call", 2), "protocol.schedule.attempts_per_call"),
        (lambda value: value["schedule"].__setitem__("timeout_or_interruption_handling", "retry"), "protocol.schedule.timeout_or_interruption_handling"),
        (lambda value: value["schedule"].__setitem__("invalid_or_unstable_handling", "drop_unstable"), "protocol.schedule.invalid_or_unstable_handling"),
        (lambda value: value["pairing"].__setitem__("arm_order", "arbitrary"), "protocol.pairing.arm_order"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_inventory"].__setitem__("call_order", "arbitrary"), "protocol.release_evidence.required_attestation.post_run_inventory"),
        (lambda value: value["pairing"]["requires_same"].__setitem__(4, "entire_prompt"), "protocol.pairing.requires_same"),
        (lambda value: value["adjudication"]["phases"]["response_utility"].__setitem__("arm_and_model_identity_visible", True), "expected {'timing': 'after_model_run'"),
        (lambda value: value["response_contract"].__setitem__("unmatched_finding_handling", "ignore_on_positive_cases"), "protocol.response_contract"),
        (lambda value: value["response_contract"]["unstable_cell_contract"].__setitem__("helpful", True), "protocol.response_contract"),
        (lambda value: value["preexecution_amendment"].__setitem__("outcome_thresholds_changed", False), "expected True"),
        (lambda value: value["statistics"]["confidence_interval"].__setitem__("seed", 1), "protocol.statistics"),
        (lambda value: value["decision"]["full_arm_absolute_thresholds"].__setitem__("precision_min", 0.5), "protocol.decision"),
        (lambda value: value["release_evidence"]["required_custody"].__setitem__("sealed", False), "custody prerequisite"),
        (lambda value: value["release_evidence"]["required_attestation"].__setitem__("signature_algorithm", "none"), "expected 'Ed25519'"),
        (lambda value: value["release_evidence"]["required_attestation"]["pre_run_binds"].append("raw_outputs"), "pre_run_binds"),
        (lambda value: value["release_evidence"]["required_attestation"]["pre_run_binds"].append("protocol"), "pre_run_binds"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_binds"].remove("raw_outputs"), "post_run_binds"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_binds"].remove("execution_journal"), "post_run_binds"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_binds"].remove("response_manifest"), "post_run_binds"),
        (lambda value: value["release_evidence"]["required_attestation"].__setitem__("corpus_commitment_format", "unbound"), "corpus_commitment_format"),
        (lambda value: value["release_evidence"]["required_attestation"].__setitem__("evaluated_skill_format", "unbound"), "evaluated_skill_format"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_inventory"].__setitem__("call_count", 1079), "post_run_inventory"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_inventory"].__setitem__("execution_journal_format", "unsigned"), "post_run_inventory"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_inventory"]["output_artifacts"].remove("mcp_journal"), "post_run_inventory"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_inventory"].__setitem__("response_manifest_signed", False), "post_run_inventory"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_inventory"].__setitem__("scorer_output_format", "unsigned_summary"), "post_run_inventory"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_inventory"].__setitem__("common_and_treatment_prompt_recomputed", False), "post_run_inventory"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_inventory"].__setitem__("runner_config_format", "unbound"), "post_run_inventory"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_inventory"].__setitem__("staged_case_manifest_matches_signed_corpus_and_mcp_session", False), "post_run_inventory"),
        (lambda value: value["release_evidence"]["required_attestation"]["post_run_inventory"].__setitem__("every_case_source_read_in_model_visible_trace", False), "post_run_inventory"),
    )
    for mutate, needle in mutations:
        changed = copy.deepcopy(protocol)
        mutate(changed)
        expect_error(lambda changed=changed: VALIDATOR.validate_protocol(changed), needle)


def test_release_cannot_freeze_without_implemented_surface() -> None:
    protocol = VALIDATOR.load_json(PROTOCOL_PATH)
    protocol["status"] = "FROZEN"
    expect_error(
        lambda: VALIDATOR.validate_protocol(protocol),
        "cannot freeze until the specified workflow has an executable",
    )


def test_valid_external_bundle_and_attestation_pass() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        verifier = trusted_verifier(root)
        VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key")


def test_corpus_mutations_fail_closed() -> None:
    mutations = (
        (lambda value: value["cases"].pop(), "exactly 120 cases"),
        (lambda value: value["cases"][1].__setitem__("case_id", value["cases"][0]["case_id"]), "unique trimmed UTF-8 ID"),
        (lambda value: value["cases"][1].__setitem__("case_id", "case-002 "), "unique trimmed UTF-8 ID"),
        (lambda value: value["cases"][1].__setitem__("case_id", "x" * 201), "unique trimmed UTF-8 ID"),
        (lambda value: value["cases"][2].__setitem__("repo_id", value["cases"][0]["repo_id"]), "more than two cases"),
        (lambda value: value["cases"][0].__setitem__("severity", "P2"), "expected 'P0'"),
        (lambda value: value["cases"][1].__setitem__("source_root", value["cases"][0]["source_root"]), "case roots must be unique and disjoint"),
        (lambda value: value["cases"][0]["source_files"].pop(), "declared hashes do not exactly cover the case root"),
        (lambda value: value["cases"][0]["source_files"][0].__setitem__("path", "../escape.ts"), "normalized bundle-relative path"),
        (lambda value: value["cases"][0]["source_files"][0].__setitem__("path", "sources/case-001/.env.local"), "credential-bearing source path"),
    )
    for mutate, needle in mutations:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_bundle(root)
            path = root / "corpus.json"
            mutate_json(path, mutate)
            refresh_manifest_ref(root, "corpus", path)
            verifier = trusted_verifier(root)
            expect_error(lambda root=root, verifier=verifier: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"), needle)


def test_source_hash_mismatch_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        (root / "sources" / "case-001" / "e2e" / "example.spec.ts").write_text("mutated after freeze\n", encoding="utf-8")
        verifier = trusted_verifier(root)
        expect_error(lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"), "SHA-256 mismatch")


def test_unlisted_case_file_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        (root / "sources" / "case-001" / "e2e" / "unlisted.spec.ts").write_text(
            "not in the signed case manifest\n", encoding="utf-8"
        )
        verifier = trusted_verifier(root)
        expect_error(
            lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"),
            "declared hashes do not exactly cover the case root",
        )


def test_labels_must_be_separate_hidden_and_complete() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        labels_path = root / "labels.json"
        mutate_json(labels_path, lambda value: value.__setitem__("model_visible", True))
        refresh_manifest_ref(root, "labels", labels_path)
        verifier = trusted_verifier(root)
        expect_error(lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"), "expected False")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        manifest = make_bundle(root)
        manifest["labels"] = manifest["corpus"]
        dump(root / "bundle.json", manifest)
        verifier = trusted_verifier(root)
        expect_error(lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"), "must be separate files")


def test_two_blinded_independent_adjudications_required() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        path = root / "adjudications.json"
        mutate_json(path, lambda value: value["records"][0]["reviewer_2"].__setitem__("reviewer_id", "human-a"))
        refresh_manifest_ref(root, "adjudications", path)
        verifier = trusted_verifier(root)
        expect_error(lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"), "must be independent")


def test_positive_admission_rejects_unlisted_valid_findings() -> None:
    for reviewer_key, invalid_value in (("reviewer_1", False), ("reviewer_2", 1)):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_bundle(root)
            path = root / "adjudications.json"
            mutate_json(path, lambda value: value["records"][0][reviewer_key].__setitem__("no_unlisted_scoring_valid_findings", invalid_value))
            refresh_manifest_ref(root, "adjudications", path)
            verifier = trusted_verifier(root)
            expect_error(
                lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"),
                "no_unlisted_scoring_valid_findings",
            )


def test_disagreement_requires_third_party_tie_break() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        path = root / "adjudications.json"
        def disagree(value: dict[str, Any]) -> None:
            value["records"][0]["reviewer_2"].update({"kind": "clean", "taxonomy_id": None, "severity": None, "accepted_locations": []})
        mutate_json(path, disagree)
        refresh_manifest_ref(root, "adjudications", path)
        verifier = trusted_verifier(root)
        expect_error(lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"), "required when reviewers disagree")


def test_oracle_location_and_resolved_label_are_bound() -> None:
    mutations = (
        (lambda value: value["labels"][0]["accepted_locations"][0].__setitem__("line", 2), "outside the hashed case sources"),
        (lambda value: value["labels"][0]["accepted_locations"][0].__setitem__("file", "other.txt"), "outside the hashed case sources"),
        (lambda value: value["labels"][0].__setitem__("taxonomy_id", "2"), "does not match the frozen corpus case"),
    )
    for mutate, needle in mutations:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_bundle(root)
            path = root / "labels.json"
            mutate_json(path, mutate)
            refresh_manifest_ref(root, "labels", path)
            verifier = trusted_verifier(root)
            expect_error(lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"), needle)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        path = root / "adjudications.json"
        def disagree_with_oracle(value: dict[str, Any]) -> None:
            record = value["records"][0]
            record["reviewer_1"]["taxonomy_id"] = "2"
            record["reviewer_2"]["taxonomy_id"] = "2"
        mutate_json(path, disagree_with_oracle)
        refresh_manifest_ref(root, "adjudications", path)
        verifier = trusted_verifier(root)
        expect_error(lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"), "does not match resolved independent adjudication")


def test_custody_manifest_is_mandatory_and_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        path = root / "custody.json"
        mutate_json(path, lambda value: value.__setitem__("sealed_before_model_run", False))
        refresh_manifest_ref(root, "custody", path)
        verifier = trusted_verifier(root)
        expect_error(lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"), "expected True")


def test_pre_run_verifier_must_accept_exact_attestation() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        verifier = trusted_verifier(root)
        verifier.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        verifier.chmod(0o700)
        expect_error(lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"), "rejected attestation")


def test_pre_run_verifier_receives_validated_protocol_digest() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        verifier = trusted_verifier(root)
        attestation = root / "isolation.attestation"
        protocol_sha256 = "a" * 64
        verifier.write_text(
            "#!/bin/sh\n"
            f"[ \"$7\" = '--protocol-sha256' ] && [ \"$8\" = '{protocol_sha256}' ] || exit 1\n"
            f"printf '%s\\n' '{{\"verified\":true,\"phase\":\"pre_run\",\"protocol_id\":\"reviewer-release-v1\",\"corpus_id\":\"external-corpus-001\",\"attestation_sha256\":\"{digest(attestation)}\"}}'\n",
            encoding="utf-8",
        )
        verifier.chmod(0o700)
        VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key", protocol_sha256)


def test_post_run_attestation_cannot_satisfy_pre_run_gate() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        make_bundle(root)
        verifier = trusted_verifier(root)
        attestation = root / "isolation.attestation"
        verifier.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' '{{\"verified\":true,\"phase\":\"post_run\",\"protocol_id\":\"reviewer-release-v1\",\"corpus_id\":\"external-corpus-001\",\"attestation_sha256\":\"{digest(attestation)}\"}}'\n",
            encoding="utf-8",
        )
        verifier.chmod(0o700)
        expect_error(
            lambda: VALIDATOR.validate_bundle(root, verifier, digest(verifier), "test-public-key"),
            "isolation verifier result.phase",
        )


def test_pre_run_verifier_ignores_ambient_path() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "bundle"
        hostile_bin = Path(directory) / "hostile-bin"
        root.mkdir()
        hostile_bin.mkdir()
        make_bundle(root)
        attestation = root / "isolation.attestation"
        helper = hostile_bin / "fake-attestation-helper"
        helper.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' '{{\"verified\":true,\"phase\":\"pre_run\",\"protocol_id\":\"reviewer-release-v1\",\"corpus_id\":\"external-corpus-001\",\"attestation_sha256\":\"{digest(attestation)}\"}}'\n",
            encoding="utf-8",
        )
        helper.chmod(0o700)
        verifier = trusted_verifier(root)
        verifier.write_text("#!/bin/sh\nexec fake-attestation-helper\n", encoding="utf-8")
        verifier.chmod(0o700)
        previous_path = os.environ.get("PATH")
        os.environ["PATH"] = f"{hostile_bin}:/usr/bin:/bin:/usr/sbin:/sbin"
        try:
            expect_error(
                lambda: VALIDATOR.validate_bundle(
                    root, verifier, digest(verifier), "test-public-key"
                ),
                "rejected attestation",
            )
        finally:
            if previous_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = previous_path


def test_cli_refuses_release_ready_without_bundle() -> None:
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), "--bundle", "/definitely/missing/reviewer-release-v1",
         "--expected-protocol-sha256", digest(PROTOCOL_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "pre-execution readiness validation requires" in completed.stderr


def test_cli_refuses_unpinned_or_changed_protocol() -> None:
    for arguments, expected in (
        ([], "independently pinned protocol SHA-256"),
        (["--expected-protocol-sha256", "0" * 64], "independently pinned snapshot"),
    ):
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), "--bundle", "/definitely/missing/reviewer-release-v1", *arguments],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        assert completed.returncode != 0
        assert expected in completed.stderr
    protocol_only = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), "--protocol-only",
         "--expected-protocol-sha256", "0" * 64],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    assert protocol_only.returncode != 0
    assert "independently pinned snapshot" in protocol_only.stderr


def test_preexecution_validator_never_certifies_complete_release_result() -> None:
    for status, result in (("COMPLETE", "PASS"), ("COMPLETE", "FAIL"), ("FROZEN", "PASS")):
        protocol = copy.deepcopy(VALIDATOR.load_json(PROTOCOL_PATH))
        protocol["status"] = status
        protocol["result"] = result
        try:
            VALIDATOR.validate_protocol(protocol)
        except VALIDATOR.ValidationError as exc:
            assert "cannot verify" in str(exc), str(exc)
        else:
            raise AssertionError(f"pre-execution validator accepted {status}/{result}")

    protocol = copy.deepcopy(VALIDATOR.load_json(PROTOCOL_PATH))
    protocol["status"] = "FROZEN"
    for invalid_value in (3, False):
        mutated = copy.deepcopy(protocol)
        mutated["current_evidence"]["model_reports"] = invalid_value
        try:
            VALIDATOR.validate_protocol(mutated)
        except VALIDATOR.ValidationError as exc:
            assert "model_reports before execution" in str(exc), str(exc)
        else:
            raise AssertionError("pre-execution validator accepted an invalid model report count")


def main() -> None:
    tests = [
        test_protocol_snapshot_binds_exact_parsed_bytes,
        test_protocol_only_accepts_pending_contract,
        test_protocol_rejects_duplicate_keys,
        test_protocol_mutations_fail_closed,
        test_release_cannot_freeze_without_implemented_surface,
        test_valid_external_bundle_and_attestation_pass,
        test_corpus_mutations_fail_closed,
        test_source_hash_mismatch_fails_closed,
        test_unlisted_case_file_fails_closed,
        test_labels_must_be_separate_hidden_and_complete,
        test_two_blinded_independent_adjudications_required,
        test_positive_admission_rejects_unlisted_valid_findings,
        test_disagreement_requires_third_party_tie_break,
        test_oracle_location_and_resolved_label_are_bound,
        test_custody_manifest_is_mandatory_and_fail_closed,
        test_pre_run_verifier_must_accept_exact_attestation,
        test_pre_run_verifier_receives_validated_protocol_digest,
        test_post_run_attestation_cannot_satisfy_pre_run_gate,
        test_pre_run_verifier_ignores_ambient_path,
        test_cli_refuses_release_ready_without_bundle,
        test_cli_refuses_unpinned_or_changed_protocol,
        test_preexecution_validator_never_certifies_complete_release_result,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print(f"reviewer release-v1 validator tests: {len(tests)} passed")


if __name__ == "__main__":
    main()

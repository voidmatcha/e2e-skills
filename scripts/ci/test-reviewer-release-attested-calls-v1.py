#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline wiring and mutation checks for signed-call reconciliation."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_attested_calls_test", ROOT / "scripts/evals/verify-reviewer-release-attested-calls-v1.py",
)
assert SPEC and SPEC.loader
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "release_validator_fixture_for_attested_calls", ROOT / "scripts/ci/test-reviewer-release-v1.py",
)
assert FIXTURE_SPEC and FIXTURE_SPEC.loader
FIXTURE = importlib.util.module_from_spec(FIXTURE_SPEC)
FIXTURE_SPEC.loader.exec_module(FIXTURE)


def ref(bundle: Path, path: Path) -> dict[str, str]:
    return {"path": path.relative_to(bundle).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def rejects(action, error=CHECK.AttestedCallError) -> None:
    try:
        action()
    except error:
        return
    raise AssertionError(f"expected {error.__name__}")


def fixture(bundle: Path, *, signed_score: dict | None = None) -> tuple[Path, Path, str]:
    protocol = json.loads((ROOT / "scripts/evals/reviewer-release-v1-protocol.json").read_bytes())
    protocol["status"] = "FROZEN"
    protocol["evaluation_surface"]["status"] = "IMPLEMENTED"
    protocol_path = bundle.parent / "frozen-protocol.json"
    protocol_path.write_bytes(CHECK.EXECUTOR.ASSEMBLE.json_bytes(protocol))
    manifest = FIXTURE.make_bundle(bundle)
    commitment_path = bundle / "corpus_commitment.json"
    commitment_path.write_bytes(CHECK.EXECUTOR.ASSEMBLE.json_bytes({
        "schema_version": 1, "protocol_id": "reviewer-release-v1", "corpus_id": "external-corpus-001",
        "corpus": manifest["corpus"],
        "labels": manifest["labels"],
        "adjudications": manifest["adjudications"],
        "custody": manifest["custody"],
    }))
    response_path = bundle / "response_manifest.json"
    response_path.write_bytes(b"{}")
    ledger_path = bundle / "adjudication_ledger.json"
    ledger_path.write_bytes(b"{}")
    scorer_path = bundle / "scorer_output.json"
    scorer_path.write_bytes(CHECK.EXECUTOR.ASSEMBLE.json_bytes(
        signed_score if signed_score is not None else {"score": "synthetic-only"},
    ))
    claim = {"schema_version": 1, "phase": "post_run", "protocol_id": "reviewer-release-v1",
             "corpus_id": "external-corpus-001", "bindings": {
                 "corpus_commitment": ref(bundle, commitment_path),
                 "evaluated_skill": {"path": "skill.json", "sha256": "0" * 64},
                 "all_inputs": {"path": "all_inputs.json", "sha256": "0" * 64},
                 "raw_outputs": {"path": "raw_outputs.json", "sha256": "0" * 64},
                 "response_manifest": ref(bundle, response_path),
                 "adjudication_ledger": ref(bundle, ledger_path),
                 "scorer_output": ref(bundle, scorer_path),
             }}
    raw_claim = CHECK.EXECUTOR.ASSEMBLE.json_bytes(claim)
    attestation = bundle / "post_run_attestation.json"
    attestation.write_bytes(CHECK.EXECUTOR.ASSEMBLE.json_bytes({
        "payload_base64": base64.b64encode(raw_claim).decode(),
        "signature_base64": base64.b64encode(b"synthetic-only").decode(),
    }))
    return protocol_path, attestation, hashlib.sha256(attestation.read_bytes()).hexdigest()


def test_pending_protocol_stops_before_verifier() -> None:
    with tempfile.TemporaryDirectory(prefix="release-attested-") as temporary:
        bundle = Path(temporary).resolve()
        attestation = bundle / "absent.json"
        attestation.write_bytes(b"{}")
        with patch.object(CHECK.EXECUTOR, "clean_evaluated_tree"), \
             patch.object(CHECK.subprocess, "run") as runner:
            rejects(lambda: CHECK.verify(
                bundle=bundle,
                protocol_path=ROOT / "scripts/evals/reviewer-release-v1-protocol.json",
                expected_protocol_sha256=hashlib.sha256(
                    (ROOT / "scripts/evals/reviewer-release-v1-protocol.json").read_bytes(),
                ).hexdigest(),
                attestation=attestation, verifier_path=Path("/usr/bin/true"),
            ))
            runner.assert_not_called()


def test_protocol_pin_refuses_before_signature_verification() -> None:
    with tempfile.TemporaryDirectory(prefix="release-attested-") as temporary:
        bundle = Path(temporary).resolve() / "bundle"
        bundle.mkdir()
        protocol, attestation, _ = fixture(bundle)
        with patch.object(CHECK.EXECUTOR, "clean_evaluated_tree"), \
             patch.object(CHECK.subprocess, "run") as runner:
            try:
                CHECK.verify(
                    bundle=bundle, protocol_path=protocol,
                    expected_protocol_sha256="0" * 64,
                    attestation=attestation, verifier_path=Path("/usr/bin/true"),
                )
            except CHECK.EXECUTOR.ExecutorError as exc:
                assert "independently pinned snapshot" in str(exc)
            else:
                raise AssertionError("mismatched protocol pin was accepted")
            runner.assert_not_called()


def test_signed_then_reconciled_and_mutations_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="release-attested-") as temporary:
        bundle = Path(temporary).resolve() / "bundle"
        bundle.mkdir()
        protocol, attestation, digest = fixture(bundle)
        protocol_digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
        result = {"verified": True, "phase": "post_run", "protocol_id": "reviewer-release-v1",
                  "corpus_id": "external-corpus-001", "attestation_sha256": digest}
        trusted = subprocess.CompletedProcess([], 0, CHECK.EXECUTOR.ASSEMBLE.json_bytes(result), b"")
        with patch.object(CHECK.EXECUTOR, "clean_evaluated_tree"), \
             patch.object(CHECK.VALIDATE, "validate_protocol"), \
             patch.object(CHECK.WITNESS, "checked_verifier", return_value="/usr/bin/true"), \
             patch.object(CHECK.subprocess, "run", return_value=trusted) as runner, \
             patch.object(CHECK.EVIDENCE, "verify_matrix", return_value={
                 "status": "byte_consistency_only", "verified_calls": 1080, "release_eligible": False,
             }) as reconciler, \
             patch.object(CHECK.POSTRUN, "resolve_ledger", return_value={"resolved_utility_rows": []}) as ledger_resolver, \
             patch.object(CHECK.MATRIX, "score", return_value={"score": "synthetic-only"}) as scorer:
            accepted = CHECK.verify(bundle=bundle, protocol_path=protocol,
                                    expected_protocol_sha256=protocol_digest,
                                    attestation=attestation, verifier_path=Path("/usr/bin/true"))
            assert accepted == {"status": "SIGNED_BYTES_RECONCILED", "verified_calls": 1080,
                                "score_reconciled": True, "release_eligible": False,
                                "independent_online_timing_proven": False}
            assert runner.call_count == 1 and reconciler.call_count == 1
            assert ledger_resolver.call_count == 1 and scorer.call_count == 1
            assert runner.call_args.args[0][1:3] == ["--phase", "post_run"]

            with patch.object(CHECK.MATRIX, "score", return_value={"score": "different"}):
                rejects(lambda: CHECK.verify(bundle=bundle, protocol_path=protocol,
                                             expected_protocol_sha256=protocol_digest,
                                             attestation=attestation, verifier_path=Path("/usr/bin/true")))

            outside = bundle.parent / "outside.json"
            outside.write_bytes(attestation.read_bytes())
            rejects(lambda: CHECK.verify(bundle=bundle, protocol_path=protocol,
                                         expected_protocol_sha256=protocol_digest,
                                         attestation=outside, verifier_path=Path("/usr/bin/true")))
            assert runner.call_count == 2

            ledger_path = bundle / "adjudication_ledger.json"
            original_ledger = ledger_path.read_bytes()
            ledger_path.write_bytes(b'{"tampered":true}')
            rejects(lambda: CHECK.verify(bundle=bundle, protocol_path=protocol,
                                         expected_protocol_sha256=protocol_digest,
                                         attestation=attestation, verifier_path=Path("/usr/bin/true")),
                    CHECK.EVIDENCE.CallEvidenceError)
            ledger_path.write_bytes(original_ledger)

            source = bundle / "sources/case-001/e2e/example.spec.ts"
            original_source = source.read_bytes()
            source.write_bytes(b"mutated after the signed corpus was prepared\n")
            rejects(lambda: CHECK.verify(bundle=bundle, protocol_path=protocol,
                                         expected_protocol_sha256=protocol_digest,
                                         attestation=attestation, verifier_path=Path("/usr/bin/true")),
                    CHECK.VALIDATE.ValidationError)
            assert reconciler.call_count == 3
            source.write_bytes(original_source)

            def mutate_after_verification(*_args, **_kwargs):
                attestation.write_bytes(b"changed after signature verification")
                return trusted

            with patch.object(CHECK.subprocess, "run", side_effect=mutate_after_verification):
                rejects(lambda: CHECK.verify(bundle=bundle, protocol_path=protocol,
                                             expected_protocol_sha256=protocol_digest,
                                             attestation=attestation, verifier_path=Path("/usr/bin/true")))
            assert reconciler.call_count == 3


def test_signed_score_comparison_preserves_json_types() -> None:
    with tempfile.TemporaryDirectory(prefix="release-attested-") as temporary:
        bundle = Path(temporary).resolve() / "bundle"
        bundle.mkdir()
        protocol, attestation, digest = fixture(bundle, signed_score={"score": True})
        trusted = subprocess.CompletedProcess([], 0, CHECK.EXECUTOR.ASSEMBLE.json_bytes({
            "verified": True, "phase": "post_run", "protocol_id": "reviewer-release-v1",
            "corpus_id": "external-corpus-001", "attestation_sha256": digest,
        }), b"")
        with patch.object(CHECK.EXECUTOR, "clean_evaluated_tree"), \
             patch.object(CHECK.VALIDATE, "validate_protocol"), \
             patch.object(CHECK.WITNESS, "checked_verifier", return_value="/usr/bin/true"), \
             patch.object(CHECK.subprocess, "run", return_value=trusted), \
             patch.object(CHECK.EVIDENCE, "verify_matrix", return_value={
                 "status": "byte_consistency_only", "verified_calls": 1080, "release_eligible": False,
             }), \
             patch.object(CHECK.POSTRUN, "resolve_ledger", return_value={"resolved_utility_rows": []}), \
             patch.object(CHECK.MATRIX, "score", return_value={"score": 1}):
            rejects(lambda: CHECK.verify(
                bundle=bundle, protocol_path=protocol,
                expected_protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),
                attestation=attestation, verifier_path=Path("/usr/bin/true"),
            ))


def main() -> None:
    test_pending_protocol_stops_before_verifier()
    test_protocol_pin_refuses_before_signature_verification()
    test_signed_then_reconciled_and_mutations_refused()
    test_signed_score_comparison_preserves_json_types()
    print("reviewer release attested calls v1: PASS (synthetic signature wiring only)")


if __name__ == "__main__":
    main()

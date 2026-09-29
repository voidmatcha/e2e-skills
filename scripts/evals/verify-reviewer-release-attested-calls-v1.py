#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reconcile a signed post-run bundle with all 1,080 raw call transcripts.

This verifies bound bytes and signatures, not independent online timing,
runner isolation, human adjudication, or the release-effect decision.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from typing import Any


HERE = Path(__file__).resolve().parent


def load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXECUTOR = load("release_attested_executor", "execute-reviewer-release-v1.py")
VALIDATE = EXECUTOR.VALIDATE
CAPTURE = EXECUTOR.CAPTURE
WITNESS = EXECUTOR.WITNESS
EVIDENCE = EXECUTOR.EVIDENCE
POSTRUN = load("release_attested_postrun", "validate-reviewer-release-postrun-v1.py")
MATRIX = load("release_attested_matrix", "score-reviewer-release-matrix-v1.py")


class AttestedCallError(ValueError):
    pass


def signed_post_run_claim(bundle: Path, attestation: Path, expected_sha256: str) -> dict[str, Any]:
    checked_attestation_path(bundle, attestation)
    raw = CAPTURE.regular_bytes(attestation, 1 << 20)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise AttestedCallError("post-run attestation changed after signature verification")
    envelope = EVIDENCE.exact(EVIDENCE.strict_json(raw, "post-run attestation"),
                              {"payload_base64", "signature_base64"}, "post-run attestation")
    try:
        payload = base64.b64decode(envelope["payload_base64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise AttestedCallError("post-run payload is not valid base64") from exc
    claim = EVIDENCE.exact(EVIDENCE.strict_json(payload, "signed post-run payload"),
                           {"schema_version", "phase", "protocol_id", "corpus_id", "bindings"}, "signed post-run payload")
    if claim["schema_version"] != 1 or claim["phase"] != "post_run" or claim["protocol_id"] != "reviewer-release-v1":
        raise AttestedCallError("post-run claim identity differs")
    return claim


def checked_attestation_path(bundle: Path, attestation: Path) -> None:
    if not attestation.is_absolute() or not attestation.is_relative_to(bundle):
        raise AttestedCallError("post-run attestation must be a real file inside the bundle")
    try:
        if attestation.resolve(strict=True) != attestation:
            raise AttestedCallError("post-run attestation must be a real file inside the bundle")
    except OSError as exc:
        raise AttestedCallError("post-run attestation is unavailable") from exc


def verify(*, bundle: Path, protocol_path: Path, expected_protocol_sha256: str,
           attestation: Path, verifier_path: Path) -> dict[str, Any]:
    if not bundle.is_absolute() or bundle.is_symlink() or bundle.resolve(strict=True) != bundle:
        raise AttestedCallError("evidence bundle must be an absolute real directory")
    if bundle.is_relative_to(EXECUTOR.ROOT):
        raise AttestedCallError("evidence bundle must be outside the evaluated repository")
    checked_attestation_path(bundle, attestation)
    EXECUTOR.clean_evaluated_tree()
    protocol_bytes = CAPTURE.regular_bytes(protocol_path, 1 << 20)
    protocol_sha256 = EXECUTOR.checked_protocol_digest(protocol_bytes, expected_protocol_sha256)
    protocol = EVIDENCE.strict_json(protocol_bytes, "frozen release protocol")
    VALIDATE.validate_protocol(protocol)
    if protocol["status"] != "FROZEN" or protocol["evaluation_surface"]["status"] != "IMPLEMENTED":
        raise AttestedCallError("protocol is not a frozen implemented release snapshot")
    pins = protocol["release_evidence"]["required_attestation"]
    verifier_sha256 = pins["trusted_verifier_sha256"]
    public_key = pins["preregistered_public_key_ed25519_base64"]
    verifier = WITNESS.checked_verifier(verifier_path, verifier_sha256)
    attestation_bytes = CAPTURE.regular_bytes(attestation, 1 << 20)
    expected_attestation_sha256 = hashlib.sha256(attestation_bytes).hexdigest()
    completed = subprocess.run(
        [verifier, "--phase", "post_run", "--attestation", str(attestation),
         "--bundle", str(bundle), "--public-key", public_key,
         "--protocol-sha256", protocol_sha256],
        cwd=bundle, env={}, capture_output=True, timeout=60, check=False,
    )
    if completed.returncode != 0:
        raise AttestedCallError("trusted verifier rejected the post-run signature or bound files")
    result = EVIDENCE.exact(EVIDENCE.strict_json(completed.stdout, "trusted verifier result"),
                            {"verified", "phase", "protocol_id", "corpus_id", "attestation_sha256"},
                            "trusted verifier result")
    if (result["verified"] is not True or result["phase"] != "post_run"
            or result["protocol_id"] != "reviewer-release-v1"
            or result["attestation_sha256"] != expected_attestation_sha256):
        raise AttestedCallError("trusted verifier did not confirm the exact post-run attestation")
    claim = signed_post_run_claim(bundle, attestation, expected_attestation_sha256)
    if result["corpus_id"] != claim["corpus_id"]:
        raise AttestedCallError("trusted verifier and signed claim corpus identities differ")
    if CAPTURE.regular_bytes(protocol_path, 1 << 20) != protocol_bytes:
        raise AttestedCallError("protocol changed during post-run verification")
    committed = EVIDENCE.exact(EVIDENCE.strict_json(EVIDENCE.read_bound(bundle, claim["bindings"]["corpus_commitment"], "corpus_commitment"), "signed corpus commitment"),
                               {"schema_version", "protocol_id", "corpus_id", "corpus", "labels", "adjudications", "custody"},
                               "signed corpus commitment")
    if committed["corpus_id"] != claim["corpus_id"]:
        raise AttestedCallError("signed corpus commitment identity differs")
    corpus_doc = EVIDENCE.strict_json(EVIDENCE.read_bound(bundle, committed["corpus"], "corpus"), "committed corpus")
    labels_doc = EVIDENCE.strict_json(EVIDENCE.read_bound(bundle, committed["labels"], "labels"), "committed labels")
    adjudications_doc = EVIDENCE.strict_json(EVIDENCE.read_bound(bundle, committed["adjudications"], "adjudications"), "committed adjudications")
    custody_doc = EVIDENCE.strict_json(EVIDENCE.read_bound(bundle, committed["custody"], "custody"), "committed custody")
    corpus_id, case_ids, positive_ids, sources, case_labels = VALIDATE.validate_cases(
        bundle, corpus_doc,
    )
    labels = VALIDATE.validate_labels(
        labels_doc, corpus_id, case_ids, positive_ids, sources, case_labels,
    )
    VALIDATE.validate_adjudications(
        adjudications_doc, corpus_id, case_ids, sources, labels,
    )
    VALIDATE.validate_custody(custody_doc, corpus_id)
    corpus_id, cases = EXECUTOR.admitted_cases(bundle, committed["corpus"])
    if corpus_id != claim["corpus_id"]:
        raise AttestedCallError("signed corpus and post-run claim identities differ")
    bindings = claim["bindings"]
    checked = EVIDENCE.verify_matrix(
        bundle, bindings["evaluated_skill"], bindings["all_inputs"],
        bindings["raw_outputs"], bindings["response_manifest"],
        {case_id: EVIDENCE.strict_json(raw, "signed model-visible case") for case_id, raw in cases.items()},
        corpus_id, protocol["evaluation_surface"], protocol["execution_identity"]["primary"],
    )
    if checked != {"status": "byte_consistency_only", "verified_calls": 1080, "release_eligible": False}:
        raise AttestedCallError("offline transcript reconciler did not accept the complete matrix")
    manifest = EVIDENCE.strict_json(EVIDENCE.read_bound(bundle, bindings["response_manifest"], "response_manifest"), "signed response manifest")
    ledger = EVIDENCE.strict_json(EVIDENCE.read_bound(bundle, bindings["adjudication_ledger"], "adjudication_ledger"), "signed adjudication ledger")
    signed_score = EVIDENCE.strict_json(EVIDENCE.read_bound(bundle, bindings["scorer_output"], "scorer_output"), "signed scorer output")
    resolved = POSTRUN.resolve_ledger(ledger, manifest, protocol)
    recomputed = MATRIX.score(
        corpus_doc, labels_doc,
        manifest, resolved, protocol,
    )
    if EXECUTOR.ASSEMBLE.json_bytes(signed_score) != EXECUTOR.ASSEMBLE.json_bytes(recomputed):
        raise AttestedCallError("signed scorer output differs from the adjudicated finding-level calculation")
    return {"status": "SIGNED_BYTES_RECONCILED", "verified_calls": 1080,
            "score_reconciled": True, "release_eligible": False,
            "independent_online_timing_proven": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--expected-protocol-sha256", required=True,
                        help="SHA-256 preregistered outside the bundle and evaluated tree")
    parser.add_argument("--post-run-attestation", type=Path, required=True)
    parser.add_argument("--attestation-verifier", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(bundle=args.bundle, protocol_path=args.protocol,
                        expected_protocol_sha256=args.expected_protocol_sha256,
                        attestation=args.post_run_attestation, verifier_path=args.attestation_verifier)
    except (AttestedCallError, EXECUTOR.ExecutorError, VALIDATE.ValidationError,
            CAPTURE.CaptureError, WITNESS.WitnessError, EVIDENCE.CallEvidenceError,
            POSTRUN.LedgerError, MATRIX.MatrixScoreError,
            OSError, subprocess.TimeoutExpired, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "INCONCLUSIVE", "error": type(exc).__name__,
                          "release_eligible": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

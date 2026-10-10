#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Candidate release-v1 call coordinator; never emits a release verdict.

The current protocol deliberately cannot pass release admission. An external
operator still has to supply a sealed corpus, isolation, and a separate witness.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, NamedTuple
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LIB = ROOT / "scripts" / "ci" / "lib"
sys.path.insert(0, str(LIB))

from reviewer_release_case_id import is_valid_case_id  # noqa: E402


def load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PLAN = load("release_executor_plan", "run-reviewer-release-v1.py")
VALIDATE = load("release_executor_validator", "validate-reviewer-release-v1.py")
CAPTURE = load("release_executor_capture", "capture-reviewer-release-call-v1.py")
WITNESS = load("release_executor_witness", "reviewer-release-witness-v1.py")
EVIDENCE = load("release_executor_evidence", "verify-reviewer-release-calls-v1.py")
ASSEMBLE = load("release_executor_assemble", "assemble-reviewer-release-call-v1.py")


class ExecutorError(ValueError):
    """Admission or one-attempt execution failed closed."""


class Admission(NamedTuple):
    bundle: Path
    protocol: dict[str, Any]
    protocol_bytes: bytes
    protocol_sha256: str
    corpus_id: str
    cases: dict[str, bytes]
    evaluated_skill_ref: dict[str, str]
    evaluated_skill: dict[str, dict[str, str]]
    runner: str
    verifier: Path
    verifier_sha256: str
    public_key: str


def clean_evaluated_tree() -> None:
    completed = subprocess.run(
        ["/usr/bin/git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT, env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        capture_output=True, timeout=30, check=False,
    )
    if completed.returncode != 0 or completed.stdout:
        raise ExecutorError("evaluated repository must be a clean committed tree")


def checked_protocol_digest(raw: bytes, expected_sha256: str) -> str:
    if (not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None):
        raise ExecutorError("independently pinned protocol SHA-256 is invalid")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ExecutorError("protocol differs from the independently pinned snapshot")
    return actual


def signed_claim(bundle: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    attestation = VALIDATE.validate_ref(bundle, manifest["isolation"]["pre_run_attestation"], "bundle.isolation.pre_run_attestation")
    envelope = EVIDENCE.exact(EVIDENCE.strict_json(CAPTURE.regular_bytes(attestation, 1 << 20), "pre-run attestation"),
                              {"payload_base64", "signature_base64"}, "pre-run attestation")
    try:
        payload = base64.b64decode(envelope["payload_base64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ExecutorError("signed pre-run payload is not base64") from exc
    claim = EVIDENCE.exact(EVIDENCE.strict_json(payload, "signed pre-run payload"),
                           {"schema_version", "phase", "protocol_id", "corpus_id", "bindings"}, "signed pre-run payload")
    if claim["schema_version"] != 1 or claim["phase"] != "pre_run" or claim["protocol_id"] != "reviewer-release-v1":
        raise ExecutorError("signed pre-run claim identity differs")
    return claim


def admitted_cases(bundle: Path, corpus_ref: dict[str, str]) -> tuple[str, dict[str, bytes]]:
    corpus_path = VALIDATE.validate_ref(bundle, corpus_ref, "bundle.corpus")
    corpus = EVIDENCE.exact(EVIDENCE.strict_json(CAPTURE.regular_bytes(corpus_path, 16 << 20), "signed corpus"),
                            {"schema_version", "protocol_id", "corpus_id", "frozen_at", "cases"}, "signed corpus")
    if corpus["schema_version"] != 1 or corpus["protocol_id"] != "reviewer-release-v1" or not isinstance(corpus["cases"], list) or len(corpus["cases"]) != 120:
        raise ExecutorError("signed corpus shape differs")
    cases: dict[str, bytes] = {}
    for raw in corpus["cases"]:
        if not isinstance(raw, dict) or set(raw) != {"case_id", "repo_id", "framework", "kind", "source_root", "source_files", "taxonomy_id", "severity", "guard_taxonomy_ids"}:
            raise ExecutorError("signed case shape differs")
        case_id = raw["case_id"]
        model_visible = {"source_root": raw["source_root"], "source_files": raw["source_files"]}
        EVIDENCE.case_files(model_visible, "model-visible case")
        if not is_valid_case_id(case_id) or case_id in cases:
            raise ExecutorError("signed case identity differs")
        cases[case_id] = ASSEMBLE.json_bytes(model_visible)
    PLAN.ordered_call_keys(list(cases))
    return corpus["corpus_id"], cases


def admit(*, bundle: Path, protocol_path: Path, expected_protocol_sha256: str,
          runner_path: Path, verifier_path: Path) -> Admission:
    """Do not create output or launch a model until all external gates pass."""
    if not bundle.is_absolute() or bundle.is_symlink() or bundle.resolve(strict=True) != bundle:
        raise ExecutorError("sealed bundle must be an absolute real directory")
    if bundle.is_relative_to(ROOT):
        raise ExecutorError("sealed bundle must be outside the evaluated repository")
    clean_evaluated_tree()
    protocol_bytes = CAPTURE.regular_bytes(protocol_path, 1 << 20)
    protocol_sha256 = checked_protocol_digest(protocol_bytes, expected_protocol_sha256)
    protocol = EVIDENCE.strict_json(protocol_bytes, "release protocol")
    VALIDATE.validate_protocol(protocol)
    if protocol["status"] != "FROZEN" or protocol["evaluation_surface"]["status"] != "IMPLEMENTED":
        raise ExecutorError("release protocol has not been frozen with an implemented executor")
    pins = protocol["release_evidence"]["required_attestation"]
    verifier_sha256 = pins["trusted_verifier_sha256"]
    public_key = pins["preregistered_public_key_ed25519_base64"]
    primary = protocol["execution_identity"]["primary"]
    if primary["runner_family"] != "codex" or primary["model"] != "gpt-5.6-sol":
        raise ExecutorError("capture command does not implement the frozen primary runner and model")
    WITNESS.checked_verifier(verifier_path, verifier_sha256)
    runner = CAPTURE.checked_executable(runner_path)
    PLAN.protocol_schedule(protocol)
    PLAN.run_validator(protocol_path, bundle, False, str(verifier_path), expected_protocol_sha256)
    if CAPTURE.regular_bytes(protocol_path, 1 << 20) != protocol_bytes:
        raise ExecutorError("protocol changed during admission")
    manifest = VALIDATE.load_json(bundle / "bundle.json")
    claim = signed_claim(bundle, manifest)
    corpus_id, cases = admitted_cases(bundle, manifest["corpus"])
    if claim["corpus_id"] != corpus_id:
        raise ExecutorError("signed claim and corpus identity differ")
    skill_ref = claim["bindings"]["evaluated_skill"]
    skill_path = VALIDATE.validate_ref(bundle, skill_ref, "signed evaluated skill")
    snapshot = EVIDENCE.evaluated_skill_snapshot(
        CAPTURE.regular_bytes(skill_path, EVIDENCE.LIMITS["evaluated_skill"]), protocol["evaluation_surface"],
    )
    for name, digest in snapshot["skill_files"].items():
        source = CAPTURE.BROKER.safe_source_bytes(ROOT, CAPTURE.BROKER.relative_path(name), 1 << 20)
        if hashlib.sha256(source).hexdigest() != digest:
            raise ExecutorError("local skill differs from the signed evaluated snapshot")
    for name, digest in snapshot["scanner_files"].items():
        source = CAPTURE.BROKER.safe_source_bytes(ROOT, CAPTURE.BROKER.relative_path(f"skills/e2e-reviewer/scripts/{name}"), 1 << 20)
        if hashlib.sha256(source).hexdigest() != digest:
            raise ExecutorError("local scanner differs from the signed evaluated snapshot")
    return Admission(bundle, protocol, protocol_bytes, protocol_sha256, corpus_id, cases,
                     skill_ref, snapshot, runner, verifier_path, verifier_sha256, public_key)


def call_row(key: tuple[str, str, int], artifacts: dict[str, dict[str, str]]) -> dict[str, Any]:
    return {"case_id": key[0], "arm": key[1], "repetition": key[2], "artifacts": artifacts}


def run_matrix(admission: Admission, *, socket_path: Path, witness_artifact_gid: int) -> dict[str, Any]:
    """Capture all calls once; failure leaves the bundle non-resumable/inconclusive."""
    bundle = admission.bundle
    artifact_gid = CAPTURE.checked_witness_artifact_gid(witness_artifact_gid)
    bundle_info = bundle.stat()
    if (bundle_info.st_gid != artifact_gid
            or bundle_info.st_mode & 0o070 != 0o050
            or bundle_info.st_mode & 0o027):
        raise ExecutorError("sealed bundle does not expose read-only group traversal to the witness")
    calls = bundle / "calls"
    CAPTURE.witness_directory(calls, artifact_gid)
    order = PLAN.ordered_call_keys(list(admission.cases))
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    first_runner_version: str | None = None
    with WITNESS.WitnessSession(
        bundle_root=bundle, case_ids=list(admission.cases), corpus_id=admission.corpus_id,
        socket_path=socket_path, verifier_path=admission.verifier,
        verifier_sha256=admission.verifier_sha256, public_key_base64=admission.public_key,
    ) as witness:
        for index, key in enumerate(order):
            clean_evaluated_tree()
            case_id, arm, repetition = key
            protocol, case, skill, scanner, prompt, case_bytes, _ = CAPTURE.prepare_input_bytes(
                bundle, admission.cases[case_id], ROOT, admission.protocol_bytes, arm,
                frozen_protocol_sha256=admission.protocol_sha256,
            )
            for name, data in skill.items():
                if hashlib.sha256(data).hexdigest() != admission.evaluated_skill["skill_files"][name]:
                    raise ExecutorError("skill bytes changed from the signed evaluated snapshot")
            for name, data in scanner.items():
                if hashlib.sha256(data).hexdigest() != admission.evaluated_skill["scanner_files"][name]:
                    raise ExecutorError("scanner bytes changed from the signed evaluated snapshot")
            with tempfile.TemporaryDirectory(prefix="reviewer-release-runner-home-") as runner_home:
                environment = CAPTURE.HOLDOUT.clean_env("codex", runner_home)
                environment["CODEX_HOME"] = str(CAPTURE.HOLDOUT.stage_codex_auth(Path(runner_home)))
                version_result = subprocess.run([admission.runner, "--version"], env=environment,
                                                capture_output=True, timeout=10, check=False)
                version = re.fullmatch(rb"codex-cli (\d+\.\d+\.\d+)\s*", version_result.stdout)
                if version_result.returncode != 0 or version is None:
                    raise ExecutorError("runner version is unavailable")
                runner_version = version.group(1).decode()
                if first_runner_version is not None and runner_version != first_runner_version:
                    raise ExecutorError("runner version changed before the next model call")
                first_runner_version = runner_version
                prepared = CAPTURE.prepare_call(
                    root=calls / f"{index:04d}", runner=admission.runner, bundle=bundle,
                    skill_root=ROOT, protocol=protocol, case=case, skill=skill,
                    scanner=scanner, prompt=prompt, case_bytes=case_bytes,
                    protocol_bytes=admission.protocol_bytes, environment=environment,
                    runner_version=runner_version, case_id=case_id,
                    arm=arm, repetition=repetition, evidence_output_root=calls,
                    witness_artifact_gid=artifact_gid,
                )
                result = CAPTURE.execute_prepared_call(
                    prepared, acknowledge_begin=lambda paths: witness.begin(key, paths),
                )
                CAPTURE.finalize_call(
                    prepared, *result, acknowledge_end=lambda paths: witness.end(key, paths),
                )
            input_paths = {role: prepared.root / "inputs" / role for role in EVIDENCE.INPUT_ROLES}
            output_paths = {role: prepared.root / "outputs" / role for role in EVIDENCE.OUTPUT_ROLES}
            inputs.append(call_row(key, WITNESS.bound_artifact_refs(bundle, input_paths, EVIDENCE.INPUT_ROLES)))
            outputs.append(call_row(key, WITNESS.bound_artifact_refs(bundle, output_paths, EVIDENCE.OUTPUT_ROLES)))
            response = EVIDENCE.strict_json(CAPTURE.regular_bytes(prepared.root / "response.json", 1 << 20), "call response")
            if EVIDENCE.call_key(response, "call response") != key:
                raise ExecutorError("response identity differs from frozen call order")
            responses.append(response)
        clean_evaluated_tree()
        if not witness.complete:
            raise ExecutorError("online witness did not complete every frozen event")
    header = {"schema_version": 1, "protocol_id": "reviewer-release-v1", "corpus_id": admission.corpus_id}
    input_path = bundle / "all_inputs.json"
    output_path = bundle / "raw_outputs.json"
    response_path = bundle / "response_manifest.json"
    CAPTURE.private_write(input_path, ASSEMBLE.json_bytes({**header, "calls": inputs}))
    CAPTURE.private_write(output_path, ASSEMBLE.json_bytes({**header, "calls": outputs}))
    CAPTURE.private_write(response_path, ASSEMBLE.json_bytes({
        "schema_version": 1, "protocol_id": "reviewer-release-v1", "evidence_class": "development_only",
        "model_run_completed_at": responses[-1]["completed_at"], "responses": responses,
    }))
    def reference(path: Path) -> dict[str, str]:
        return {"path": path.relative_to(bundle).as_posix(),
                "sha256": hashlib.sha256(CAPTURE.regular_bytes(path, 32 << 20)).hexdigest()}

    checked = EVIDENCE.verify_matrix(
        bundle, admission.evaluated_skill_ref, reference(input_path),
        reference(output_path), reference(response_path),
        {case_id: EVIDENCE.strict_json(raw, "admitted case") for case_id, raw in admission.cases.items()},
        admission.corpus_id, admission.protocol["evaluation_surface"],
        admission.protocol["execution_identity"]["primary"],
    )
    if checked != {"status": "byte_consistency_only", "verified_calls": 1080, "release_eligible": False}:
        raise ExecutorError("offline call reconciler did not accept the complete matrix")
    return {"status": "CAPTURED_UNATTESTED", "calls": len(order), "release_eligible": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--expected-protocol-sha256", required=True,
                        help="SHA-256 preregistered outside the bundle and evaluated tree")
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--attestation-verifier", type=Path, required=True)
    parser.add_argument("--witness-socket", type=Path, required=True)
    parser.add_argument("--witness-artifact-gid", type=int,
                        help="dedicated read-only artifact group shared with the independent witness")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        admission = admit(bundle=args.bundle, protocol_path=args.protocol,
                          expected_protocol_sha256=args.expected_protocol_sha256,
                          runner_path=args.runner_path, verifier_path=args.attestation_verifier)
        if not args.execute:
            result = {"status": "PREFLIGHT_ONLY", "model_execution_attempted": False}
        else:
            if args.witness_artifact_gid is None:
                raise ExecutorError("release execution requires --witness-artifact-gid")
            result = run_matrix(
                admission, socket_path=args.witness_socket,
                witness_artifact_gid=args.witness_artifact_gid,
            )
    except (ExecutorError, PLAN.ReleasePlanError, VALIDATE.ValidationError,
            CAPTURE.CaptureError, WITNESS.WitnessError, EVIDENCE.CallEvidenceError,
            CAPTURE.BROKER.ToolSurfaceError, OSError, subprocess.TimeoutExpired,
            KeyError, TypeError, ValueError) as exc:
        result = {"status": "INCONCLUSIVE", "error": type(exc).__name__,
                  "release_eligible": False, "no_replacement_call": True}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

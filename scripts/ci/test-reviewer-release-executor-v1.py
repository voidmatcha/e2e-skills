#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline admission and one-attempt checks for the release coordinator."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "reviewer_release_executor_v1", ROOT / "scripts/evals/execute-reviewer-release-v1.py",
)
assert SPEC and SPEC.loader
EXECUTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXECUTOR)


def rejects(action, error=EXECUTOR.ExecutorError) -> None:
    try:
        action()
    except error:
        return
    raise AssertionError(f"expected {error.__name__}")


def provision_witness_access(bundle: Path) -> int:
    group_id = EXECUTOR.os.getegid()
    bundle.chmod(0o2750)
    return group_id


def test_model_visible_cases() -> None:
    with tempfile.TemporaryDirectory(prefix="release-executor-") as temporary:
        bundle = Path(temporary).resolve()
        cases = []
        for index in range(120):
            case_id = f"case-{index:03d}"
            cases.append({
                "case_id": case_id, "repo_id": f"repo-{index:03d}",
                "framework": "playwright" if index < 60 else "cypress",
                "kind": "positive" if index % 2 == 0 else "clean",
                "source_root": case_id,
                "source_files": [{"path": f"{case_id}/test.spec.ts", "sha256": "0" * 64}],
                "taxonomy_id": "#1" if index % 2 == 0 else None,
                "severity": "P0" if index % 2 == 0 else None,
                "guard_taxonomy_ids": [] if index % 2 == 0 else ["#1"],
            })
        corpus = {"schema_version": 1, "protocol_id": "reviewer-release-v1",
                  "corpus_id": "sealed", "frozen_at": "2026-09-24T00:00:00Z", "cases": cases}
        raw = EXECUTOR.ASSEMBLE.json_bytes(corpus)
        corpus_path = bundle / "corpus.json"
        corpus_path.write_bytes(raw)
        identity, sanitized = EXECUTOR.admitted_cases(
            bundle, {"path": "corpus.json", "sha256": hashlib.sha256(raw).hexdigest()},
        )
        assert identity == "sealed" and len(sanitized) == 120
        assert len(EXECUTOR.PLAN.ordered_call_keys(list(sanitized))) == 1080
        for case_id, visible in sanitized.items():
            decoded = json.loads(visible)
            assert set(decoded) == {"source_root", "source_files"}
            assert decoded["source_root"] == case_id
            assert b"taxonomy_id" not in visible and b"severity" not in visible
            assert b"positive" not in visible and b"guard_taxonomy_ids" not in visible


def test_pending_protocol_refuses_before_output() -> None:
    with tempfile.TemporaryDirectory(prefix="release-executor-") as temporary:
        bundle = Path(temporary).resolve()
        with patch.object(EXECUTOR, "clean_evaluated_tree"):
            rejects(lambda: EXECUTOR.admit(
                bundle=bundle,
                protocol_path=ROOT / "scripts/evals/reviewer-release-v1-protocol.json",
                expected_protocol_sha256=hashlib.sha256(
                    (ROOT / "scripts/evals/reviewer-release-v1-protocol.json").read_bytes(),
                ).hexdigest(),
                runner_path=Path("/usr/bin/true"), verifier_path=Path("/usr/bin/true"),
            ))
        assert list(bundle.iterdir()) == []


def test_protocol_pin_refuses_before_bundle_admission() -> None:
    with tempfile.TemporaryDirectory(prefix="release-executor-") as temporary:
        bundle = Path(temporary).resolve()
        with patch.object(EXECUTOR, "clean_evaluated_tree"), \
             patch.object(EXECUTOR.PLAN, "run_validator") as validator:
            try:
                EXECUTOR.admit(
                    bundle=bundle,
                    protocol_path=ROOT / "scripts/evals/reviewer-release-v1-protocol.json",
                    expected_protocol_sha256="0" * 64,
                    runner_path=Path("/usr/bin/true"), verifier_path=Path("/usr/bin/true"),
                )
            except EXECUTOR.ExecutorError as exc:
                assert "independently pinned snapshot" in str(exc)
            else:
                raise AssertionError("mismatched protocol pin was accepted")
            validator.assert_not_called()
        assert list(bundle.iterdir()) == []


def test_private_bundle_refuses_before_call_directory() -> None:
    with tempfile.TemporaryDirectory(prefix="release-executor-") as temporary:
        bundle = Path(temporary).resolve()
        bundle.chmod(0o700)
        admission = EXECUTOR.Admission(
            bundle=bundle, protocol={}, protocol_bytes=b"{}", protocol_sha256="0" * 64,
            corpus_id="sealed", cases={}, evaluated_skill_ref={},
            evaluated_skill={"skill_files": {}, "scanner_files": {}},
            runner="/usr/bin/true", verifier=Path("/usr/bin/true"),
            verifier_sha256="0" * 64, public_key="unused",
        )
        rejects(lambda: EXECUTOR.run_matrix(
            admission, socket_path=bundle / "witness.sock",
            witness_artifact_gid=EXECUTOR.os.getegid(),
        ))
        assert not (bundle / "calls").exists()


def test_begin_refusal_stops_before_next_call() -> None:
    witness_instances = []

    class RefusingWitness:
        complete = False

        def __init__(self, **_kwargs):
            self.begins = 0
            witness_instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def begin(self, _key, _paths):
            self.begins += 1
            raise EXECUTOR.WITNESS.WitnessError("begin refused")

    with tempfile.TemporaryDirectory(prefix="release-executor-") as temporary:
        bundle = Path(temporary).resolve()
        cases = {f"case-{index:03d}": b"{}" for index in range(120)}
        protocol = json.loads(
            (ROOT / "scripts/evals/reviewer-release-v1-protocol.json").read_bytes(),
        )
        admission = EXECUTOR.Admission(
            bundle=bundle,
            protocol=protocol,
            protocol_bytes=b"{}", protocol_sha256="0" * 64,
            corpus_id="sealed", cases=cases, evaluated_skill_ref={},
            evaluated_skill={"skill_files": {}, "scanner_files": {}},
            runner="/usr/bin/true", verifier=Path("/usr/bin/true"),
            verifier_sha256="0" * 64, public_key="unused",
        )
        case = {
            "source_root": "case-000",
            "source_files": [{"path": "case-000/test.spec.ts", "sha256": "0" * 64}],
        }
        case_bytes = EXECUTOR.ASSEMBLE.json_bytes(case)
        prompt = EXECUTOR.CAPTURE.CALL.PROMPT.build_prompt(
            protocol["evaluation_surface"], case, "no-skill", {},
        )

        def fake_prepare_input_bytes(*_args, **_kwargs):
            return protocol, case, {}, {}, prompt, case_bytes, b"{}"

        with patch.object(EXECUTOR, "clean_evaluated_tree"), \
             patch.object(EXECUTOR.PLAN, "ordered_call_keys",
                          return_value=[("case-000", "no-skill", 1)]), \
             patch.object(EXECUTOR.WITNESS, "WitnessSession", RefusingWitness), \
             patch.object(EXECUTOR.CAPTURE, "prepare_input_bytes", fake_prepare_input_bytes), \
             patch.object(EXECUTOR.CAPTURE.HOLDOUT, "clean_env", return_value={}), \
             patch.object(EXECUTOR.CAPTURE.HOLDOUT, "stage_codex_auth", side_effect=lambda path: path), \
             patch.object(EXECUTOR.CAPTURE.subprocess, "Popen") as launcher, \
             patch.object(EXECUTOR.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"codex-cli 0.155.1\n", b"")):
            rejects(lambda: EXECUTOR.run_matrix(
                admission, socket_path=bundle / "witness.sock",
                witness_artifact_gid=provision_witness_access(bundle),
            ),
                    EXECUTOR.WITNESS.WitnessError)
        launcher.assert_not_called()
        assert len(witness_instances) == 1 and witness_instances[0].begins == 1
        first = bundle / "calls/0000"
        assert set(path.name for path in (first / "inputs").iterdir()) == set(EXECUTOR.EVIDENCE.INPUT_ROLES)
        assert not (first / "attempt.json").exists()
        assert not (bundle / "calls/0001").exists()


def test_final_tree_check_precedes_aggregate_publication() -> None:
    events: list[tuple[str, tuple[str, str, int]]] = []
    dirty = False

    class RecordingWitness:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @property
        def complete(self):
            return len(events) == 2

        def begin(self, key, _paths):
            events.append(("begin", key))

        def end(self, key, _paths):
            events.append(("end", key))

    with tempfile.TemporaryDirectory(prefix="release-executor-") as temporary:
        bundle = Path(temporary).resolve()
        cases = {f"case-{index:03d}": b"{}" for index in range(120)}
        admission = EXECUTOR.Admission(
            bundle=bundle,
            protocol={"evaluation_surface": {}, "execution_identity": {"primary": {}}},
            protocol_bytes=b"{}", protocol_sha256="0" * 64,
            corpus_id="sealed", cases=cases, evaluated_skill_ref={},
            evaluated_skill={"skill_files": {}, "scanner_files": {}},
            runner="/usr/bin/true", verifier=Path("/usr/bin/true"),
            verifier_sha256="0" * 64, public_key="unused",
        )
        key = ("case-000", "no-skill", 1)

        def check_tree():
            if dirty:
                raise EXECUTOR.ExecutorError("evaluated tree changed during execution")

        def fake_prepare_call(**kwargs):
            root = kwargs["root"]
            root.mkdir(mode=0o700)
            return SimpleNamespace(root=root, key=key)

        def fake_execute(prepared, *, acknowledge_begin):
            acknowledge_begin({})
            return 0, b"", b""

        def fake_finalize(prepared, *_result, acknowledge_end):
            nonlocal dirty
            acknowledge_end({})
            (prepared.root / "response.json").write_bytes(EXECUTOR.ASSEMBLE.json_bytes({
                "case_id": key[0], "arm": key[1], "repetition": key[2],
                "valid": False, "raw_output_sha256": "0" * 64,
                "normalized_finding_identities": [],
                "completed_at": "2026-09-24T00:00:00Z",
            }))
            dirty = True

        def fake_refs(bundle_root, paths, roles):
            return {role: {"path": path.relative_to(bundle_root).as_posix(), "sha256": "0" * 64}
                    for role, path in paths.items() if role in roles}

        with patch.object(EXECUTOR, "clean_evaluated_tree", side_effect=check_tree), \
             patch.object(EXECUTOR.PLAN, "ordered_call_keys", return_value=[key]), \
             patch.object(EXECUTOR.WITNESS, "WitnessSession", RecordingWitness), \
             patch.object(EXECUTOR.WITNESS, "bound_artifact_refs", fake_refs), \
             patch.object(EXECUTOR.CAPTURE, "prepare_input_bytes", return_value=({}, {}, {}, {}, b"prompt", b"{}", b"{}")), \
             patch.object(EXECUTOR.CAPTURE, "prepare_call", fake_prepare_call), \
             patch.object(EXECUTOR.CAPTURE, "execute_prepared_call", fake_execute), \
             patch.object(EXECUTOR.CAPTURE, "finalize_call", fake_finalize), \
             patch.object(EXECUTOR.CAPTURE.HOLDOUT, "clean_env", return_value={}), \
             patch.object(EXECUTOR.CAPTURE.HOLDOUT, "stage_codex_auth", side_effect=lambda path: path), \
             patch.object(EXECUTOR.EVIDENCE, "verify_matrix") as reconciler, \
             patch.object(EXECUTOR.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"codex-cli 0.155.1\n", b"")):
            rejects(lambda: EXECUTOR.run_matrix(
                admission, socket_path=bundle / "witness.sock",
                witness_artifact_gid=provision_witness_access(bundle),
            ))

        assert events == [("begin", key), ("end", key)]
        reconciler.assert_not_called()
        for name in ("all_inputs.json", "raw_outputs.json", "response_manifest.json"):
            assert not (bundle / name).exists()


def test_full_schedule_uses_distinct_call_roots_and_online_boundaries() -> None:
    events: list[tuple[str, tuple[str, str, int]]] = []
    roots: list[Path] = []
    homes: list[str] = []

    class RecordingWitness:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @property
        def complete(self):
            return len(events) == 2160

        def begin(self, key, _paths):
            events.append(("begin", key))

        def end(self, key, _paths):
            events.append(("end", key))

    with tempfile.TemporaryDirectory(prefix="release-executor-") as temporary:
        bundle = Path(temporary).resolve()
        cases = {f"case-{index:03d}": b"{}" for index in range(120)}
        admission = EXECUTOR.Admission(
            bundle=bundle,
            protocol={"evaluation_surface": {}, "execution_identity": {"primary": {}}},
            protocol_bytes=b"{}", protocol_sha256="0" * 64,
            corpus_id="sealed", cases=cases, evaluated_skill_ref={},
            evaluated_skill={"skill_files": {}, "scanner_files": {}},
            runner="/usr/bin/true", verifier=Path("/usr/bin/true"),
            verifier_sha256="0" * 64, public_key="unused",
        )

        def fake_prepare_call(**kwargs):
            root = kwargs["root"]
            root.mkdir(mode=0o700)
            roots.append(root)
            homes.append(kwargs["environment"]["CODEX_HOME"])
            return SimpleNamespace(root=root, key=(kwargs["case_id"], kwargs["arm"], kwargs["repetition"]))

        def fake_execute(prepared, *, acknowledge_begin):
            acknowledge_begin({})
            assert events[-1] == ("begin", prepared.key)
            return 0, b"", b""

        def fake_finalize(prepared, *_result, acknowledge_end):
            acknowledge_end({})
            assert events[-1] == ("end", prepared.key)
            case_id, arm, repetition = prepared.key
            (prepared.root / "response.json").write_bytes(EXECUTOR.ASSEMBLE.json_bytes({
                "case_id": case_id, "arm": arm, "repetition": repetition,
                "valid": False, "raw_output_sha256": "0" * 64,
                "normalized_finding_identities": [],
                "completed_at": "2026-09-24T00:00:00Z",
            }))

        def fake_refs(bundle_root, paths, roles):
            return {role: {"path": path.relative_to(bundle_root).as_posix(), "sha256": "0" * 64}
                    for role, path in paths.items() if role in roles}

        with patch.object(EXECUTOR, "clean_evaluated_tree"), \
             patch.object(EXECUTOR.WITNESS, "WitnessSession", RecordingWitness), \
             patch.object(EXECUTOR.WITNESS, "bound_artifact_refs", fake_refs), \
             patch.object(EXECUTOR.CAPTURE, "prepare_input_bytes", return_value=({}, {}, {}, {}, b"prompt", b"{}", b"{}")), \
             patch.object(EXECUTOR.CAPTURE, "prepare_call", fake_prepare_call), \
             patch.object(EXECUTOR.CAPTURE, "execute_prepared_call", fake_execute), \
             patch.object(EXECUTOR.CAPTURE, "finalize_call", fake_finalize), \
             patch.object(EXECUTOR.CAPTURE.HOLDOUT, "clean_env", return_value={}), \
             patch.object(EXECUTOR.CAPTURE.HOLDOUT, "stage_codex_auth", side_effect=lambda path: path), \
             patch.object(EXECUTOR.EVIDENCE, "verify_matrix", return_value={
                 "status": "byte_consistency_only", "verified_calls": 1080, "release_eligible": False,
             }) as reconciler, \
             patch.object(EXECUTOR.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"codex-cli 0.155.1\n", b"")):
            result = EXECUTOR.run_matrix(
                admission, socket_path=bundle / "witness.sock",
                witness_artifact_gid=provision_witness_access(bundle),
            )

        assert result == {"status": "CAPTURED_UNATTESTED", "calls": 1080, "release_eligible": False}
        order = EXECUTOR.PLAN.ordered_call_keys(list(cases))
        assert events == [event for key in order for event in (("begin", key), ("end", key))]
        assert roots == [bundle / "calls" / f"{index:04d}" for index in range(1080)]
        assert len(set(homes)) == 1080 and reconciler.call_count == 1
        for name in ("all_inputs.json", "raw_outputs.json", "response_manifest.json"):
            assert (bundle / name).is_file()


def main() -> None:
    test_model_visible_cases()
    test_pending_protocol_refuses_before_output()
    test_protocol_pin_refuses_before_bundle_admission()
    test_private_bundle_refuses_before_call_directory()
    test_begin_refusal_stops_before_next_call()
    test_final_tree_check_precedes_aggregate_publication()
    test_full_schedule_uses_distinct_call_roots_and_online_boundaries()
    print("reviewer release executor v1: PASS (offline refusal and synthetic 1080-call schedule only)")


if __name__ == "__main__":
    main()

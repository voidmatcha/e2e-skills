#!/usr/bin/env python3
"""Focused tests for the reviewer-release-v1 preflight planner."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-release-v1.py"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"
SPEC = importlib.util.spec_from_file_location("reviewer_release_v1_runner", RUNNER_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
PROMPT_PATH = ROOT / "scripts/evals/reviewer-release-prompt-v1.py"
PROMPT_SPEC = importlib.util.spec_from_file_location("reviewer_release_v1_prompt", PROMPT_PATH)
assert PROMPT_SPEC and PROMPT_SPEC.loader
PROMPT = importlib.util.module_from_spec(PROMPT_SPEC)
PROMPT_SPEC.loader.exec_module(PROMPT)
SMOKE_PATH = ROOT / "scripts/evals/smoke-reviewer-release-codex-mcp-v1.py"
SMOKE_SPEC = importlib.util.spec_from_file_location("reviewer_release_codex_smoke_v1", SMOKE_PATH)
assert SMOKE_SPEC and SMOKE_SPEC.loader
SMOKE = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(SMOKE)


def invoke(*args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    completed = subprocess.run(
        [sys.executable, str(RUNNER_PATH), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.stderr == "", completed.stderr
    lines = completed.stdout.splitlines()
    assert len(lines) == 1, completed.stdout
    return completed, json.loads(lines[0])


def main() -> None:
    protocol_result, protocol_payload = invoke("--protocol-only")
    assert protocol_result.returncode == 0
    assert protocol_payload["status"] == "PROTOCOL_VALID"
    assert protocol_payload["execution_plan"] is None

    protocol = RUNNER.load_json(PROTOCOL_PATH)
    surface = protocol["evaluation_surface"]
    case = {"source_root": "sources/case-001", "source_files": [{
        "path": "sources/case-001/example.spec.ts", "sha256": "a" * 64,
    }]}
    common = PROMPT.common_prompt(surface, case)
    assert common.count(b"3b | Cypress uncaught:exception suppression | P0") == 1
    assert b'for example "7", never "#7"' in common
    assert common.count(b"sources/case-001/example.spec.ts") == 1
    full_file = {"skills/e2e-reviewer/SKILL.md": b"Full treatment marker"}
    catalog_file = {"skills/e2e-reviewer/references/pattern-reference.md": b"Catalog treatment marker"}
    full_prompt = PROMPT.build_prompt(surface, case, "full", full_file)
    catalog_prompt = PROMPT.build_prompt(surface, case, "catalog-only", catalog_file)
    no_skill_prompt = PROMPT.build_prompt(surface, case, "no-skill", {})
    assert full_prompt.startswith(common) and catalog_prompt.startswith(common)
    assert no_skill_prompt == common
    try:
        PROMPT.common_prompt({**surface, "common_taxonomy_index_sha256": "0" * 64}, case)
    except PROMPT.PromptError:
        pass
    else:
        raise AssertionError("taxonomy index drift entered the common prompt")
    assert b"Full treatment marker" in full_prompt and b"Catalog treatment marker" not in full_prompt
    assert b"Catalog treatment marker" in catalog_prompt and b"Full treatment marker" not in catalog_prompt
    assert b"treatment marker" not in no_skill_prompt.lower()
    smoke_case = {"source_root": "sources/case-001", "source_files": [{
        "path": SMOKE.SOURCE_PATH, "sha256": hashlib.sha256(SMOKE.SOURCE).hexdigest(),
    }]}
    call_evidence = SMOKE.load_call_evidence()
    for arm in ("full", "catalog-only", "no-skill"):
        initial = {path: (ROOT / path).read_bytes() for path in surface["initial_model_visible_files"][arm]}
        assert SMOKE.exact_task_prompt(call_evidence, surface, smoke_case, arm) == PROMPT.build_prompt(surface, smoke_case, arm, initial)
        two_file_case = {**smoke_case, "source_files": [*smoke_case["source_files"], {
            "path": SMOKE.SECOND_SOURCE_PATH, "sha256": hashlib.sha256(SMOKE.SECOND_SOURCE).hexdigest(),
        }]}
        two_file_prompt = SMOKE.exact_task_prompt(call_evidence, surface, two_file_case, arm)
        assert two_file_prompt.count(SMOKE.SECOND_SOURCE_PATH.encode()) == 1
    try:
        PROMPT.build_prompt(surface, case, "no-skill", full_file)
    except PROMPT.PromptError:
        pass
    else:
        raise AssertionError("no-skill accepted treatment material")
    try:
        PROMPT.common_prompt(surface, {**case, "source_files": [*case["source_files"], *case["source_files"]]})
    except PROMPT.PromptError:
        pass
    else:
        raise AssertionError("duplicate source path entered the common task prompt")
    plan = RUNNER.protocol_schedule(protocol)
    assert plan["arms"] == ["full", "catalog-only", "no-skill"]
    assert RUNNER.ordered_arms("case-001", 1) == ("catalog-only", "no-skill", "full")
    assert RUNNER.ordered_arms("case-001", 2) == ("no-skill", "catalog-only", "full")
    assert RUNNER.ordered_arms("line\u2028sep", 1) == ("no-skill", "full", "catalog-only")
    assert RUNNER.ordered_arms("para\u2029sep", 1) == ("no-skill", "catalog-only", "full")
    assert RUNNER.ordered_arms(r"literal\u2028", 1) == ("catalog-only", "full", "no-skill")
    for invalid_id, invalid_repetition in (
        ("", 1), ("case-001", 0), ("\ud800", 1), ("case-001 ", 1),
        ("x" * 201, 1), ("é" * 101, 1), ("\u3000case-001", 1),
    ):
        try:
            RUNNER.ordered_arms(invalid_id, invalid_repetition)
        except RUNNER.ReleasePlanError:
            pass
        else:
            raise AssertionError("invalid call-order input was accepted")
    assert RUNNER.ordered_arms("é" * 100, 1)
    call_keys = RUNNER.ordered_call_keys([f"case-{index:03d}" for index in range(120)])
    assert len(call_keys) == len(set(call_keys)) == 1080
    assert call_keys[:3] == [("case-000", arm, 1) for arm in RUNNER.ordered_arms("case-000", 1)]
    assert {(case_id, arm, repetition) for case_id, arm, repetition in call_keys} == {
        (f"case-{index:03d}", arm, repetition)
        for index in range(120) for arm in ("full", "catalog-only", "no-skill") for repetition in (1, 2, 3)
    }
    assert plan["independent_case_count"] == 120
    assert plan["repetitions_count_as_independent_cases"] is False
    assert plan["host_model_count"] == 1
    assert plan["cell_count"] == 3
    assert plan["planned_model_invocations"] == 1080
    assert plan["per_call_wall_timeout_seconds"] == 600
    assert plan["attempts_per_call"] == 1
    assert plan["timeout_or_interruption_handling"] == "inconclusive_no_replacement_call"
    assert [cell["planned_invocations"] for cell in plan["cells"]] == [360, 360, 360]

    missing_bundle, payload = invoke(
        "--attestation-verifier", sys.executable,
        "--runner-path", f"codex-gpt-5.6-sol={sys.executable}",
        "--dry-run",
    )
    assert missing_bundle.returncode == 2
    assert payload["status"] == "BLOCKED"
    assert "--bundle is required" in payload["error"]

    with tempfile.TemporaryDirectory(prefix="reviewer-release-runner-v1-") as raw:
        temp = Path(raw)
        artifacts = temp / "testbed"
        artifacts.mkdir(mode=0o700)
        target = artifacts / "exact-task-smoke"
        content = {"prompt.txt": b"synthetic prompt\n", "staged/case/example.spec.ts": SMOKE.SOURCE}
        hashes = SMOKE.persist_artifacts(target, content, artifacts)
        assert hashes == {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        assert manifest == {"status": "DEVELOPMENT_ONLY", "sha256": hashes}
        assert os.stat(target).st_mode & 0o777 == 0o700
        assert all(os.stat(target / name).st_mode & 0o777 == 0o600 for name in [*content, "manifest.json"])
        try:
            SMOKE.persist_artifacts(target, content, artifacts)
        except ValueError:
            pass
        else:
            raise AssertionError("development artifact was overwritten")
        (artifacts / "linked").symlink_to(target, target_is_directory=True)
        for unsafe in (artifacts / "linked" / "child", artifacts / ".." / "outside", artifacts / "bad-file"):
            if unsafe.name == "bad-file":
                unsafe.write_text("existing", encoding="utf-8")
            try:
                SMOKE.validate_artifact_target(unsafe, artifacts)
            except ValueError:
                pass
            else:
                raise AssertionError(f"unsafe artifact destination accepted: {unsafe}")
        try:
            SMOKE.persist_artifacts(artifacts / "invalid-files", {"../escape": b"x"}, artifacts)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe artifact filename accepted")
        assert not (artifacts / "invalid-files").exists()
        incomplete = artifacts / "incomplete"
        incomplete.mkdir(mode=0o700)
        (incomplete / "manifest.json").write_text(json.dumps({"status": "DEVELOPMENT_ONLY", "sha256": {}}), encoding="utf-8")
        try:
            SMOKE.replay_artifacts(incomplete)
        except ValueError as exc:
            assert "missing required files" in str(exc)
        else:
            raise AssertionError("incomplete development trace replayed")
        required = ("prompt.txt", "codex.jsonl", "codex.stderr", "final.txt", "mcp-transcript.jsonl", "case.json", "protocol.json", SMOKE.SOURCE_PATH, "transcript-report.json")
        digest_map = {}
        for name in required:
            path = incomplete / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic")
            digest_map[name] = hashlib.sha256(b"synthetic").hexdigest()
        digest_map["prompt.txt"] = "0" * 64
        (incomplete / "manifest.json").write_text(json.dumps({"status": "DEVELOPMENT_ONLY", "sha256": digest_map}), encoding="utf-8")
        try:
            SMOKE.replay_artifacts(incomplete)
        except ValueError as exc:
            assert "digest mismatch" in str(exc)
        else:
            raise AssertionError("tampered development trace replayed")
        bundle = temp / "bundle"
        bundle.mkdir()
        marker = temp / "model-was-called"
        model_runner = temp / "trusted-model-runner"
        model_runner.write_text(f"#!/bin/sh\ntouch {marker}\nexit 99\n", encoding="utf-8")
        model_runner.chmod(0o755)
        original_validate = RUNNER.run_validator
        RUNNER.run_validator = lambda *_args, **_kwargs: {"mode": "pre-execution-ready", "status": "PASS"}
        try:
            args = argparse.Namespace(
                protocol=PROTOCOL_PATH,
                bundle=bundle,
                attestation_verifier=Path(sys.executable),
                expected_protocol_sha256=hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest(),
                runner_path=[f"codex-gpt-5.6-sol={model_runner}"],
                protocol_only=False,
                dry_run=True,
            )
            payload = RUNNER.execute(args)
        finally:
            RUNNER.run_validator = original_validate
        assert payload["status"] == "EXECUTION_PREREQUISITES_VALID"
        assert payload["next_action"] == "EXECUTOR_NOT_IMPLEMENTED"
        assert payload["model_execution_attempted"] is False
        assert not marker.exists(), "preflight planner invoked the model runner"

    no_primary = json.loads(json.dumps(protocol))
    no_primary["execution_identity"]["primary"] = {}
    try:
        RUNNER.protocol_schedule(no_primary)
    except RUNNER.ReleasePlanError as exc:
        assert "execution_identity.primary" in str(exc)
    else:
        raise AssertionError("missing primary identity must fail closed")

    unknown, payload = invoke("--not-a-real-flag")
    assert unknown.returncode == 2
    assert payload["status"] == "BLOCKED"
    assert "argument error" in payload["error"]

    print("reviewer release runner v1 tests: 8 passed")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Deterministic tests for the fresh-context curated subset-review runner."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-independent-review.py"
PROTOCOL_PATH = ROOT / "scripts/evals/independent-review-protocol-v5.json"
EXPECTED_SELECTED_FILES = [
    "README.md",
    "SECURITY.md",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".codex-plugin/plugin.json",
    "skills/playwright-test-generator/SKILL.md",
    "skills/e2e-reviewer/SKILL.md",
    "skills/playwright-debugger/SKILL.md",
    "skills/cypress-debugger/SKILL.md",
    "skills/e2e-reviewer/references/pattern-reference.md",
    "skills/e2e-reviewer/references/verification-rules.md",
    "skills/e2e-reviewer/scripts/scan.sh",
    "skills/playwright-test-generator/scripts/preflight_target.py",
    "skills/playwright-test-generator/scripts/run-preflight-target.sh",
    "skills/playwright-test-generator/scripts/run-raw-aria-snapshot.sh",
    "skills/playwright-test-generator/scripts/raw-aria-snapshot.cjs",
    "skills/playwright-debugger/scripts/read-playwright-artifact.py",
    "skills/playwright-debugger/scripts/publish-json-report.py",
    "skills/playwright-debugger/scripts/download-playwright-report.py",
    "skills/cypress-debugger/scripts/read-cypress-artifact.py",
    "skills/cypress-debugger/scripts/extract-junit-failures.py",
    "skills/cypress-debugger/scripts/download-cypress-reports.py",
    "skills/cypress-debugger/scripts/publish-mochawesome-report.py",
    "skills/cypress-debugger/scripts/redact_artifact.py",
    "skills/playwright-test-generator/best-practices.md",
    "skills/playwright-test-generator/code-rules.md",
    "skills/playwright-test-generator/verification-rules.md",
    "skills/e2e-reviewer/references/upstream-rule-sources.md",
    "scripts/ci/ci-local.sh",
    "scripts/ci/pre-push-security.sh",
]


def load_runner():
    spec = importlib.util.spec_from_file_location("independent_review_tested", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner()


def review_payload(
    packet: dict,
    *,
    score: int = 95,
    findings: list[dict] | None = None,
    verdict: str = "PASS",
) -> dict:
    dimensions = [item["id"] for item in packet["rubric"]["dimensions"]]
    return {
        "summary": "Independent packet-only synthetic assessment.",
        "scores": {dimension: score for dimension in dimensions},
        "findings": findings or [],
        "limitations": ["Synthetic contract test; no model was called."],
        "verdict": verdict,
    }


def assert_packet_is_deterministic_and_unanchored() -> tuple[dict, dict, dict]:
    assert RUNNER.sha256_file(PROTOCOL_PATH) == RUNNER.V5_PROTOCOL_HASH
    protocol = RUNNER.load_protocol(PROTOCOL_PATH)
    assert protocol["schedule"]["attempts"] == [
        {
            "attempt_id": f"codex-high-fix-r{repetition}",
            "schedule_index": repetition - 1,
            "repetition": repetition,
            "runner": "codex",
            "model": "gpt-5.6-sol",
            "provider_family": "openai",
        }
        for repetition in range(1, 4)
    ]
    assert protocol["phase_binding"] == RUNNER.PHASE_BINDING
    assert protocol["phase_binding"]["predecessor_protocol_sha256"] == (
        "93bd84b4a33da03abb81e718068691846901a3beacadb439cf8762b040eeae42"
    )
    assert protocol["phase_binding"]["predecessor_packet_sha256"] == (
        "fb19f5846a7bd5a8cb7e5bb3c49287f136761b91e12481025e1f3040245c03b3"
    )
    packet_a, manifest_a = RUNNER.build_packet(ROOT, protocol)
    packet_b, manifest_b = RUNNER.build_packet(ROOT, protocol)
    assert packet_a == packet_b
    assert manifest_a == manifest_b
    assert manifest_a["included_representation_bytes"] <= manifest_a[
        "representation_byte_budget"
    ]
    assert manifest_a["representation_byte_budget"] == 850_000
    assert manifest_a["included_representation_bytes"] == sum(
        item["transformed_source_bytes"] for item in manifest_a["selected_files"]
    )
    assert manifest_a["included_original_source_bytes"] == sum(
        item["original_source_bytes"] for item in manifest_a["selected_files"]
    )
    assert manifest_a["remaining_representation_bytes"] == (
        manifest_a["representation_byte_budget"]
        - manifest_a["included_representation_bytes"]
    )
    paths = [item["path"] for item in manifest_a["selected_files"]]
    assert paths == EXPECTED_SELECTED_FILES
    assert len(paths) == 30
    assert len(paths) == len(set(paths))
    assert all(required for _path, required in RUNNER.FILE_ALLOWLIST)
    assert manifest_a["omissions"]["allowlist"] == []
    assert "scripts/ci/ci-local.sh" in paths
    assert "scripts/ci/pre-push-security.sh" in paths
    readme_manifest = next(
        item for item in manifest_a["selected_files"] if item["path"] == "README.md"
    )
    assert readme_manifest["transformed_source_bytes"] < readme_manifest[
        "original_source_bytes"
    ]
    assert readme_manifest["representation_bytes"] > readme_manifest[
        "transformed_source_bytes"
    ]
    for path in paths:
        lowered = path.casefold()
        assert "/evals/" not in f"/{lowered}/"
        assert "holdout" not in lowered
        assert "scorecard" not in lowered
        assert "benchmarks/" not in lowered
        assert "/reviews/" not in f"/{lowered}/"
    readme = next(item["content"] for item in packet_a["files"] if item["path"] == "README.md")
    for heading in RUNNER.README_EXCLUDED_HEADINGS:
        assert heading not in readme
    assert "v3 public-development holdout" not in readme
    assert "scorecard was not fully blind" not in readme
    dimension_ids = [item["id"] for item in packet_a["rubric"]["dimensions"]]
    assert dimension_ids == [
        "semantic_correctness",
        "false_positive_control",
        "security_trust_boundaries",
        "verification_design",
        "scope_contract_consistency",
        "docs_usability",
    ]
    assert "runtime_evidence" not in dimension_ids
    assert "benchmark_integrity" not in dimension_ids
    assert all(
        item["review_question"].strip()
        for item in packet_a["rubric"]["dimensions"]
    )
    prompt = RUNNER.render_prompt(packet_a, protocol)
    assert "Score contract and verification design, not observed runtime success" in prompt
    assert "Do not infer results from" in prompt
    for item in packet_a["rubric"]["dimensions"]:
        assert item["review_question"] in prompt
    # Line-numbering integrity: a retained heading must appear in the packet at its real README
    # line. The anchor is derived rather than hard-coded — the previous literal ("## At a glance")
    # outlived the heading and turned this check into a StopIteration.
    anchor_number, anchor_text = next(
        (index, line)
        for index, line in enumerate(
            (ROOT / "README.md").read_text(encoding="utf-8").splitlines(), start=1
        )
        if line.startswith("## ")
        and line.removeprefix("## ").strip() not in RUNNER.README_EXCLUDED_HEADINGS
    )
    assert f"{anchor_number:06d} | {anchor_text}" in readme
    return protocol, packet_a, manifest_a


def assert_synthetic_statuses(protocol: dict, packet: dict) -> None:
    passing = review_payload(packet)
    parsed = RUNNER.parse_review(json.dumps(passing), packet, protocol)
    status, decision = RUNNER.derive_decision(parsed, protocol)
    assert status == "PASS"
    assert decision["overall_score"] == 95

    file_item = packet["manifest"]["selected_files"][0]
    high = {
        "severity": "H",
        "category": "semantic_correctness",
        "file": file_item["path"],
        "line": 1,
        "title": "Material defect",
        "evidence": "The cited line provides synthetic evidence.",
        "recommendation": "Repair the bounded defect.",
    }
    failing = review_payload(packet, findings=[high], verdict="FAIL")
    parsed = RUNNER.parse_review(json.dumps(failing), packet, protocol)
    status, decision = RUNNER.derive_decision(parsed, protocol)
    assert status == "FAIL"
    assert decision["finding_counts"]["H"] == 1

    try:
        RUNNER.parse_review('{"summary":"x","summary":"y"}', packet, protocol)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate-key output must be INCONCLUSIVE")

    bad_line = review_payload(packet)
    bad_line["findings"] = [{**high, "severity": "M", "line": 0}]
    try:
        RUNNER.parse_review(json.dumps(bad_line), packet, protocol)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid evidence line must be INCONCLUSIVE")

    stale_dimensions = review_payload(packet)
    stale_dimensions["scores"]["runtime_evidence"] = stale_dimensions["scores"].pop(
        "verification_design"
    )
    try:
        RUNNER.parse_review(json.dumps(stale_dimensions), packet, protocol)
    except ValueError:
        pass
    else:
        raise AssertionError("obsolete unanswerable rubric dimension was accepted")


def assert_cli_synthetic_pass_fail_inconclusive(packet: dict) -> None:
    host = [
        "--runner",
        "codex",
        "--model",
        "gpt-5.6-sol",
        "--attempt-id",
        "codex-high-fix-r1",
    ]
    with tempfile.TemporaryDirectory(prefix="independent-review-ci-") as raw:
        temp = Path(raw)
        invocation_ids: list[str] = []
        cases = {
            "pass": (review_payload(packet), 0, "PASS"),
            "fail": (review_payload(packet, score=80, verdict="FAIL"), 1, "FAIL"),
            "inconclusive": ({"not": "the contract"}, 2, "INCONCLUSIVE"),
        }
        for name, (payload, expected_code, expected_status) in cases.items():
            output = temp / name
            synthetic = temp / f"{name}.json"
            synthetic.write_text(json.dumps(payload), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER_PATH),
                    "--output-dir",
                    str(output),
                    *host,
                    "--synthetic-output",
                    str(synthetic),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
            assert proc.returncode == expected_code, proc.stderr or proc.stdout
            report_path = output / "report-codex-high-fix-r1.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            assert report["status"] == expected_status
            assert report["integrity_before"] == report["integrity_after"]
            assert report["runner_identity"]["mode"] == "synthetic"
            assert report["model_tool_surface"] == "none"
            assert report["artifact_integrity_eligible"] is False
            assert "independent_evidence_eligible" not in report
            assert report["local_artifact_integrity_passed"] is True
            assert report["caller_declared_runner_model_provenance"] is True
            assert report["remote_model_attestation"] is False
            assert any(
                "cannot attest that a distinct remote model call occurred"
                in limitation
                for limitation in report["limitations"]
            )
            assert report["attempt_id"] == "codex-high-fix-r1"
            assert report["schedule_index"] == 0
            assert report["repetition"] == 1
            assert report["declared_schedule_digest"] == RUNNER.schedule_digest(
                RUNNER.SCHEDULE_VERSION,
                RUNNER.SCHEDULE_SEED,
                RUNNER.expected_schedule_attempts(),
            )
            assert report["started_at_utc"].endswith("Z")
            assert report["finished_at_utc"].endswith("Z")
            assert report["started_at_utc"] <= report["finished_at_utc"]
            invocation = uuid.UUID(report["invocation_id"])
            assert invocation.version == 4
            assert str(invocation) == report["invocation_id"]
            invocation_ids.append(report["invocation_id"])
            assert report["credential_environment"] == "not-used-synthetic"
            assert report["raw_output_exact"] is True
            assert Path(report["raw_output_path"]).is_file()
            manifest_path = Path(report["packet_manifest_path"])
            frozen_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert frozen_manifest["packet_sha256"] == report["integrity_before"][
                "packet_sha256"
            ]
        assert len(invocation_ids) >= 2
        assert len(invocation_ids) == len(set(invocation_ids))


def assert_credential_lookup_failure_writes_report() -> None:
    with tempfile.TemporaryDirectory(
        prefix="independent-review-credential-failure-"
    ) as raw:
        output = Path(raw) / "output"
        args = SimpleNamespace(
            protocol=PROTOCOL_PATH,
            output_dir=output,
            prepare_only=False,
            runner="codex",
            model="gpt-5.6-sol",
            attempt_id="codex-high-fix-r1",
            synthetic_output=None,
            runner_path=None,
            timeout=1,
        )
        with patch.object(
            RUNNER.SHARED,
            "resolve_runner_executable",
            return_value=sys.executable,
        ), patch.object(
            RUNNER.SHARED,
            "command_output",
            return_value="synthetic Codex CLI identity",
        ), patch.object(
            RUNNER.SHARED,
            "inherited_runner_credentials",
            side_effect=ValueError("secret-bearing lookup detail"),
        ):
            result, exit_code = RUNNER.run_review(args)
        assert exit_code == 2
        assert result["status"] == "INCONCLUSIVE"
        assert result["status_reason"] == {
            "code": "credential_staging_error",
            "message": "runner credentials could not be staged",
        }
        assert result["credential_environment"] == (
            "credential-staging-failed-model-tools-disabled"
        )
        assert "secret-bearing lookup detail" not in json.dumps(result)
        report_path = output / "report-codex-high-fix-r1.json"
        raw_path = output / "raw-codex-high-fix-r1.json"
        assert report_path.is_file()
        assert raw_path.is_file()
        persisted = json.loads(report_path.read_text(encoding="utf-8"))
        assert persisted == result
        assert persisted["raw_output_exact"] is True


def assert_live_integrity_eligibility_is_narrow(packet: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="independent-review-live-contract-") as raw:
        output = Path(raw) / "output"
        args = SimpleNamespace(
            protocol=PROTOCOL_PATH,
            output_dir=output,
            prepare_only=False,
            runner="codex",
            model="gpt-5.6-sol",
            attempt_id="codex-high-fix-r1",
            synthetic_output=None,
            runner_path=None,
            timeout=1,
        )
        with patch.object(
            RUNNER.SHARED,
            "resolve_runner_executable",
            return_value=sys.executable,
        ), patch.object(
            RUNNER.SHARED,
            "command_output",
            return_value="synthetic live-mode CLI identity",
        ), patch.object(
            RUNNER.SHARED,
            "inherited_runner_credentials",
            return_value={},
        ), patch.object(
            RUNNER.SHARED,
            "run_once",
            return_value=(0, json.dumps(review_payload(packet)), 5),
        ):
            result, exit_code = RUNNER.run_review(args)
        assert exit_code == 0
        assert result["status"] == "PASS"
        assert result["execution_mode"] == "live"
        assert result["local_artifact_integrity_passed"] is True
        assert result["artifact_integrity_eligible"] is True
        assert result["caller_declared_runner_model_provenance"] is True
        assert result["remote_model_attestation"] is False


def assert_public_claude_auth_contract_matches_runner() -> None:
    docs = (ROOT / "docs/ai-reviewer-benchmark.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert (
        "Claude receives exactly one validated\n"
        "`CLAUDE_CODE_OAUTH_TOKEN` snapshot"
    ) in docs
    assert "it does not inherit\n`CLAUDE_CONFIG_DIR`, `ANTHROPIC_API_KEY`" in docs
    assert "No API-key, OAuth-token, or cloud-credential variables are forwarded" not in docs
    for text in (docs, security):
        assert "`CLAUDE_CODE_OAUTH_TOKEN` snapshot" in text
        assert "`CLAUDE_CONFIG_DIR`, `ANTHROPIC_API_KEY`" in text
    assert "Claude may receive\n`CLAUDE_CONFIG_DIR`" not in security

    token = "claude-contract-" + ("x" * 40)
    with patch.dict(
        os.environ,
        {
            "CLAUDE_CODE_OAUTH_TOKEN": token,
            "CLAUDE_CONFIG_DIR": "/ambient/claude",
            "ANTHROPIC_API_KEY": "sk-ant-" + ("y" * 40),
        },
        clear=True,
    ):
        environment = RUNNER.SHARED.clean_env("claude", "/tmp/runner-home")
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in environment
    assert "CLAUDE_CONFIG_DIR" not in environment
    assert "ANTHROPIC_API_KEY" not in environment

    command, stdin = RUNNER.SHARED.runner_invocation(
        "claude", "/trusted/claude", "prompt", None
    )
    tools_index = command.index("--tools")
    assert command[tools_index + 1] == ""
    assert stdin == "prompt"


def assert_anchoring_files_cannot_enter_allowlist() -> None:
    hostile = (
        "benchmarks/raw.json",
        "scripts/evals/labeled.json",
        "docs/scorecard.md",
        "docs/prior-review.md",
        ".git/config",
    )
    for path in hostile:
        try:
            RUNNER.validate_relative_product_path(path)
        except ValueError:
            continue
        raise AssertionError(f"excluded anchoring path was accepted: {path}")


def assert_fixed_protocol_rejects_metric_drift(protocol: dict) -> None:
    drifted = json.loads(json.dumps(protocol))
    drifted["rubric"]["decision"]["overall_score_min"] = 80
    try:
        RUNNER.validate_protocol(drifted)
    except ValueError:
        pass
    else:
        raise AssertionError("weakened review threshold was accepted")

    redefined = json.loads(json.dumps(protocol))
    redefined["rubric"]["dimensions"][3]["review_question"] = (
        "Infer whether omitted runtime executions passed."
    )
    try:
        RUNNER.validate_protocol(redefined)
    except ValueError:
        pass
    else:
        raise AssertionError("redefined packet-only rubric question was accepted")

    changed_freeze = json.loads(json.dumps(protocol))
    changed_freeze["packet"]["freeze_policy"] += " Semantic mutation."
    try:
        RUNNER.validate_protocol(changed_freeze)
    except ValueError:
        pass
    else:
        raise AssertionError("changed packet freeze policy was accepted")

    for field, replacement in (
        ("predecessor_protocol_sha256", "0" * 64),
        ("predecessor_packet_sha256", "1" * 64),
    ):
        rebound = json.loads(json.dumps(protocol))
        rebound["phase_binding"][field] = replacement
        try:
            RUNNER.validate_protocol(rebound)
        except ValueError:
            pass
        else:
            raise AssertionError(f"drifted phase binding was accepted: {field}")

    rebound_attempt = json.loads(json.dumps(protocol))
    rebound_attempt["phase_binding"]["predecessor_attempts"][0]["report_sha256"] = (
        "2" * 64
    )
    try:
        RUNNER.validate_protocol(rebound_attempt)
    except ValueError:
        pass
    else:
        raise AssertionError("drifted immutable baseline attempt binding was accepted")


def assert_protocol_bytes_are_pinned() -> None:
    with tempfile.TemporaryDirectory(prefix="independent-review-protocol-pin-") as raw:
        changed = Path(raw) / "independent-review-protocol-v5.json"
        changed.write_bytes(PROTOCOL_PATH.read_bytes() + b"\n")
        try:
            RUNNER.load_protocol(changed)
        except ValueError as exc:
            assert "preregistered v5 SHA-256" in str(exc)
        else:
            raise AssertionError("whitespace-rehashed v5 protocol was accepted")
        output = Path(raw) / "output"
        proc = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--protocol",
                str(changed),
                "--output-dir",
                str(output),
                "--prepare-only",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        assert proc.returncode == 2
        assert "preregistered v5 SHA-256" in proc.stderr
        assert not (output / "prepared.json").exists()


def assert_fixed_schedule_rejects_drift(protocol: dict) -> None:
    mutations = []

    duplicate = json.loads(json.dumps(protocol))
    duplicate["schedule"]["attempts"][1]["attempt_id"] = "codex-high-fix-r1"
    mutations.append(("duplicate schedule IDs", duplicate))

    bad_order = json.loads(json.dumps(protocol))
    bad_order["schedule"]["attempts"][0], bad_order["schedule"]["attempts"][1] = (
        bad_order["schedule"]["attempts"][1],
        bad_order["schedule"]["attempts"][0],
    )
    mutations.append(("bad schedule order", bad_order))

    bad_repetition = json.loads(json.dumps(protocol))
    bad_repetition["schedule"]["attempts"][1]["repetition"] = 1
    mutations.append(("bad repetition", bad_repetition))

    non_integer_index = json.loads(json.dumps(protocol))
    non_integer_index["schedule"]["attempts"][0]["schedule_index"] = False
    mutations.append(("non-integer schedule index", non_integer_index))

    bad_binding = json.loads(json.dumps(protocol))
    bad_binding["schedule"]["attempts"][0]["model"] = "gpt-5.5"
    mutations.append(("bad runner binding", bad_binding))

    tampered_digest = json.loads(json.dumps(protocol))
    tampered_digest["schedule"]["digest"] = "0" * 64
    mutations.append(("tampered schedule digest", tampered_digest))

    for label, mutation in mutations:
        try:
            RUNNER.validate_protocol(mutation)
        except ValueError:
            continue
        raise AssertionError(f"{label} was accepted")


def assert_cli_rejects_attempt_id_drift(packet: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="independent-review-attempt-id-") as raw:
        temp = Path(raw)
        synthetic = temp / "pass.json"
        synthetic.write_text(json.dumps(review_payload(packet)), encoding="utf-8")
        base = [
            sys.executable,
            str(RUNNER_PATH),
            "--output-dir",
            str(temp / "output"),
            "--runner",
            "codex",
            "--model",
            "gpt-5.6-sol",
            "--synthetic-output",
            str(synthetic),
        ]
        cases = (
            ("missing", base),
            ("invalid", [*base, "--attempt-id", "codex-high-fix-r99"]),
            (
                "mismatched",
                [
                    *base,
                    "--runner",
                    "claude",
                    "--attempt-id",
                    "codex-high-fix-r1",
                ],
            ),
        )
        for label, command in cases:
            proc = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
            assert proc.returncode == 2, (
                f"{label} attempt ID returned {proc.returncode}: "
                f"{proc.stderr or proc.stdout}"
            )
            assert not (
                temp / "output" / "report-codex-high-fix-r1.json"
            ).exists()


def assert_source_drift_is_detected(protocol: dict, manifest: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="independent-review-drift-") as raw:
        clone = Path(raw) / "repo"
        clone.mkdir()
        for item in manifest["selected_files"]:
            source = ROOT / item["path"]
            destination = clone / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        packet, cloned_manifest = RUNNER.build_packet(clone, protocol)
        target = clone / cloned_manifest["selected_files"][0]["path"]
        target.write_bytes(target.read_bytes() + b"\n")
        packet_after, manifest_after = RUNNER.build_packet(clone, protocol)
        assert packet_after != packet
        assert manifest_after["selected_surface_sha256"] != cloned_manifest[
            "selected_surface_sha256"
        ]


def main() -> int:
    protocol, packet, manifest = assert_packet_is_deterministic_and_unanchored()
    assert_synthetic_statuses(protocol, packet)
    assert_cli_synthetic_pass_fail_inconclusive(packet)
    assert_credential_lookup_failure_writes_report()
    assert_live_integrity_eligibility_is_narrow(packet)
    assert_public_claude_auth_contract_matches_runner()
    assert_anchoring_files_cannot_enter_allowlist()
    assert_fixed_protocol_rejects_metric_drift(protocol)
    assert_protocol_bytes_are_pinned()
    assert_fixed_schedule_rejects_drift(protocol)
    assert_cli_rejects_attempt_id_drift(packet)
    assert_source_drift_is_detected(protocol, manifest)
    print("independent review tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

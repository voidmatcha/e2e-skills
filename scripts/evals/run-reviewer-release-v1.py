#!/usr/bin/env python3
"""Preflight and print the frozen reviewer-release-v1 execution plan.

This wrapper deliberately does not execute models. It gates and renders a
release schedule after the repository-owned release validator succeeds. The
release-v1 model executor has not been implemented yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "ci" / "lib"
sys.path.insert(0, str(LIB))

from reviewer_release_case_id import is_valid_case_id  # noqa: E402

DEFAULT_PROTOCOL = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"
DEFAULT_VALIDATOR = ROOT / "scripts/evals/validate-reviewer-release-v1.py"
ARMS = ("full", "catalog-only", "no-skill")
ARM_ORDER_ALGORITHM = "sha256_v1_per_case_repetition_order"


class ReleasePlanError(ValueError):
    """A fail-closed release planning error."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ReleasePlanError(f"argument error: {message}")


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReleasePlanError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleasePlanError(f"cannot load protocol: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReleasePlanError("protocol must be a JSON object")
    return payload


def require_positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReleasePlanError(f"{name} must be a positive integer")
    return value


def ordered_arms(case_id: str, repetition: int) -> tuple[str, ...]:
    """Frozen arm order: ascending SHA-256, with arm ID as an impossible-tie rule.

    Hash compact UTF-8 JSON array [protocol_id, case_id, repetition, arm].
    Case IDs are committed by the independent custodian before any run.
    """
    if not is_valid_case_id(case_id) or type(repetition) is not int or repetition not in (1, 2, 3):
        raise ReleasePlanError("arm order needs a committed case ID and repetition 1..3")
    def rank(arm: str) -> tuple[bytes, str]:
        material = json.dumps(["reviewer-release-v1", case_id, repetition, arm], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(material).digest(), arm
    return tuple(sorted(ARMS, key=rank))


def ordered_call_keys(case_ids: list[str]) -> list[tuple[str, str, int]]:
    if not isinstance(case_ids, list) or len(case_ids) != 120 or any(not is_valid_case_id(case_id) for case_id in case_ids) or len(set(case_ids)) != 120:
        raise ReleasePlanError("call schedule needs 120 distinct committed case IDs")
    return [
        (case_id, arm, repetition)
        for case_id in sorted(case_ids)
        for repetition in (1, 2, 3)
        for arm in ordered_arms(case_id, repetition)
    ]


def protocol_schedule(protocol: dict[str, Any]) -> dict[str, Any]:
    if protocol.get("protocol_id") != "reviewer-release-v1":
        raise ReleasePlanError("protocol_id must be reviewer-release-v1")

    arms_raw = protocol.get("arms")
    if not isinstance(arms_raw, list):
        raise ReleasePlanError("arms must be an array")
    arms: list[str] = []
    for index, arm in enumerate(arms_raw):
        if not isinstance(arm, dict) or not isinstance(arm.get("id"), str):
            raise ReleasePlanError(f"arms[{index}].id must be a string")
        arms.append(arm["id"])
    if arms != list(ARMS):
        raise ReleasePlanError("arms must be exactly full, catalog-only, no-skill")
    pairing = protocol.get("pairing")
    if not isinstance(pairing, dict) or pairing.get("arm_order") != ARM_ORDER_ALGORITHM:
        raise ReleasePlanError("pairing.arm_order differs from the frozen ordering algorithm")

    corpus = protocol.get("corpus")
    schedule = protocol.get("schedule")
    identity = protocol.get("execution_identity")
    if not isinstance(corpus, dict) or not isinstance(schedule, dict):
        raise ReleasePlanError("corpus and schedule must be objects")
    if not isinstance(identity, dict):
        raise ReleasePlanError("execution_identity must be an object")
    unique_cases = require_positive_int(corpus.get("unique_cases"), "corpus.unique_cases")
    repetitions = require_positive_int(
        schedule.get("repetitions_per_case_arm"),
        "schedule.repetitions_per_case_arm",
    )
    if schedule.get("repetitions_are_independent_samples") is not False:
        raise ReleasePlanError("repetitions must be stability-only, not independent samples")

    expected_identity = {"host_id", "runner_family", "model", "minimum_version"}
    primary = identity.get("primary")
    if not isinstance(primary, dict) or set(primary) != expected_identity or not all(
        isinstance(primary[key], str) and primary[key].strip() for key in expected_identity
    ):
        raise ReleasePlanError(
            "execution_identity.primary must contain non-empty "
            f"{sorted(expected_identity)} before execution"
        )
    matrix = [{key: primary[key] for key in sorted(expected_identity)}]

    declared_cases = schedule.get("unique_cases")
    if declared_cases != unique_cases:
        raise ReleasePlanError("schedule.unique_cases must match corpus.unique_cases")
    if schedule.get("arm_count") != len(arms):
        raise ReleasePlanError("schedule.arm_count must match the frozen arms")

    cells = []
    for arm in arms:
        for entry in matrix:
            cells.append(
                {
                    "arm": arm,
                    "host_id": entry["host_id"],
                    "runner_family": entry["runner_family"],
                    "model": entry["model"],
                    "minimum_version": entry["minimum_version"],
                    "unique_cases": unique_cases,
                    "repetitions_per_case": repetitions,
                    "planned_invocations": unique_cases * repetitions,
                }
            )
    planned_calls = unique_cases * repetitions * len(arms) * len(matrix)
    if schedule.get("scheduled_model_calls") != planned_calls:
        raise ReleasePlanError("schedule.scheduled_model_calls does not match the derived matrix")
    if type(schedule.get("per_call_wall_timeout_seconds")) is not int or schedule["per_call_wall_timeout_seconds"] != 600:
        raise ReleasePlanError("schedule.per_call_wall_timeout_seconds must be the frozen 600 seconds")
    if type(schedule.get("attempts_per_call")) is not int or schedule["attempts_per_call"] != 1:
        raise ReleasePlanError("schedule.attempts_per_call must be the frozen single attempt")
    if schedule.get("timeout_or_interruption_handling") != "inconclusive_no_replacement_call":
        raise ReleasePlanError("schedule.timeout_or_interruption_handling differs from the frozen policy")
    return {
        "independent_unit": "unique_case",
        "independent_case_count": unique_cases,
        "repetitions_count_as_independent_cases": False,
        "arms": arms,
        "host_model_count": len(matrix),
        "cell_count": len(cells),
        "planned_model_invocations": planned_calls,
        "per_call_wall_timeout_seconds": 600,
        "attempts_per_call": 1,
        "timeout_or_interruption_handling": "inconclusive_no_replacement_call",
        "cells": cells,
    }


def parse_runner_paths(values: list[str], required_hosts: set[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for value in values:
        host_id, separator, raw_path = value.partition("=")
        if not separator or not host_id or not raw_path:
            raise ReleasePlanError("--runner-path must use HOST_ID=/absolute/path")
        if host_id in paths:
            raise ReleasePlanError(f"duplicate --runner-path for {host_id}")
        declared = Path(raw_path)
        if not declared.is_absolute():
            raise ReleasePlanError(f"runner path for {host_id} must be absolute")
        try:
            resolved = declared.resolve(strict=True)
        except OSError as exc:
            raise ReleasePlanError(f"runner path for {host_id} is unavailable: {exc}") from exc
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise ReleasePlanError(f"runner path for {host_id} must be an executable file")
        paths[host_id] = str(resolved)
    missing = sorted(required_hosts - paths.keys())
    extra = sorted(paths.keys() - required_hosts)
    if missing or extra:
        raise ReleasePlanError(f"runner path host mismatch: missing={missing}, extra={extra}")
    return {host: paths[host] for host in sorted(paths)}


def trusted_executable(path: Path | None, name: str) -> str:
    if path is None:
        raise ReleasePlanError(f"--{name} is required for pre-execution readiness validation")
    if not path.is_absolute():
        raise ReleasePlanError(f"--{name} must be an absolute path")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ReleasePlanError(f"--{name} is unavailable: {exc}") from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ReleasePlanError(f"--{name} must be an executable file")
    return str(resolved)


def run_validator(
    protocol: Path,
    bundle: Path | None,
    protocol_only: bool,
    attestation_verifier: str | None,
    expected_protocol_sha256: str | None = None,
) -> dict[str, Any]:
    command = [sys.executable, str(DEFAULT_VALIDATOR), "--protocol", str(protocol)]
    command.extend(["--protocol-only"] if protocol_only else ["--bundle", str(bundle)])
    if attestation_verifier is not None:
        command.extend(["--attestation-verifier", attestation_verifier])
    if expected_protocol_sha256 is not None:
        command.extend(["--expected-protocol-sha256", expected_protocol_sha256])
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    expected = (
        "reviewer-release-v1 validation: PASS (protocol-only)"
        if protocol_only
        else "reviewer-release-v1 validation: PASS (pre-execution-ready)"
    )
    stdout_lines = completed.stdout.strip().splitlines()
    if completed.returncode != 0 or not stdout_lines or stdout_lines[-1] != expected:
        detail = completed.stderr.strip() or completed.stdout.strip() or "validator failed"
        raise ReleasePlanError(f"release validator did not pass: {detail[:1000]}")
    return {
        "mode": "protocol-only" if protocol_only else "pre-execution-ready",
        "status": "PASS",
    }


def parser() -> argparse.ArgumentParser:
    result = JsonArgumentParser(description=__doc__)
    result.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    result.add_argument("--bundle", type=Path)
    result.add_argument("--attestation-verifier", type=Path)
    result.add_argument("--expected-protocol-sha256")
    result.add_argument("--runner-path", action="append", default=[], metavar="HOST_ID=PATH")
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--protocol-only", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    return result


def execute(args: argparse.Namespace) -> dict[str, Any]:
    protocol = load_json(args.protocol)
    if args.protocol_only:
        if args.bundle is not None or args.runner_path or args.attestation_verifier is not None or args.expected_protocol_sha256 is not None:
            raise ReleasePlanError(
                "--protocol-only does not accept bundle, runner paths, an attestation verifier, or a protocol pin"
            )
    elif args.bundle is None:
        raise ReleasePlanError("--bundle is required for pre-execution readiness validation")
    elif args.expected_protocol_sha256 is None:
        raise ReleasePlanError("pre-execution readiness requires --expected-protocol-sha256")
    verifier = None
    if not args.protocol_only:
        verifier = trusted_executable(args.attestation_verifier, "attestation-verifier")
    validation = run_validator(
        args.protocol,
        args.bundle,
        args.protocol_only,
        verifier,
        args.expected_protocol_sha256,
    )
    if args.protocol_only:
        return {
            "schema_version": 1,
            "protocol_id": protocol.get("protocol_id"),
            "status": "PROTOCOL_VALID",
            "validation": validation,
            "execution_plan": None,
            "model_execution_attempted": False,
        }
    schedule = protocol_schedule(protocol)
    required_hosts = {cell["host_id"] for cell in schedule["cells"]}
    runner_paths = parse_runner_paths(args.runner_path, required_hosts)
    return {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "status": "EXECUTION_PREREQUISITES_VALID",
        "next_action": "EXECUTOR_NOT_IMPLEMENTED",
        "dry_run": bool(args.dry_run),
        "validation": validation,
        "runner_paths": runner_paths,
        "execution_plan": schedule,
        "model_execution_attempted": False,
    }


def main() -> int:
    try:
        args = parser().parse_args()
        result = execute(args)
    except (ReleasePlanError, OSError) as exc:
        result = {
            "schema_version": 1,
            "protocol_id": "reviewer-release-v1",
            "status": "BLOCKED",
            "error": str(exc),
            "execution_plan": None,
            "model_execution_attempted": False,
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

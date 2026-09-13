#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Freeze a passing Claude smoke and bind measured-run authorization."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess

import run_routing as confirmation


HERE = Path(__file__).resolve().parent
runner = confirmation.runner


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    freeze_path = HERE / "freeze-record.json"
    authorization_path = HERE / "execution-authorization-claude.json"
    if freeze_path.exists() or authorization_path.exists():
        raise ValueError("refusing to replace an existing freeze or authorization record")

    protocol_path = HERE / "protocol.json"
    runner_path = HERE / "run_routing.py"
    smoke_runner_path = HERE / "run_smoke.py"
    activation_path = HERE / "codex-arm-activation.json"
    case_manifest_path = HERE / "cases" / "manifest.json"
    smoke_manifest_path = HERE / "smoke" / "manifest.json"
    smoke_result_path = HERE / "smoke-results-claude.json"

    protocol = load(protocol_path)
    case_manifest = runner.validate_case_manifest(case_manifest_path, protocol, "measured")
    smoke_manifest = runner.validate_case_manifest(smoke_manifest_path, protocol, "smoke")
    smoke = load(smoke_result_path)
    smoke_checks = {
        "stage": smoke.get("stage") == "smoke",
        "host": smoke.get("host_id") == "claude",
        "status": smoke.get("status") == "COMPLETE",
        "gate": smoke.get("summary", {}).get("smoke_gate") == "PASS",
        "protocol": smoke.get("protocol_sha256") == sha(protocol_path),
        "runner": smoke.get("runner_sha256") == sha(runner_path),
        "two_cells": len(smoke.get("cells", [])) == 2,
        "both_pass": all(cell.get("status") == "PASS" for cell in smoke.get("cells", [])),
    }
    if not all(smoke_checks.values()):
        raise ValueError(f"Claude smoke gate did not pass: {smoke_checks}")

    surface = {
        "protocol_sha256": sha(protocol_path),
        "runner_sha256": sha(runner_path),
        "smoke_runner_sha256": sha(smoke_runner_path),
        "codex_activation_sha256": sha(activation_path),
        "case_manifest_sha256": sha(case_manifest_path),
        "case_tree_sha256": runner.case_tree_digest(case_manifest, case_manifest_path),
        "smoke_manifest_sha256": sha(smoke_manifest_path),
        "smoke_tree_sha256": runner.case_tree_digest(smoke_manifest, smoke_manifest_path),
        "evaluated_snapshot": protocol["evaluated_snapshot"]["sha256_at_preparation"],
        "smoke_results": {"claude": sha(smoke_result_path)},
        "confirmation_scorer_sha256": sha(HERE / "score_confirmation.py"),
        "preparation_script_sha256": sha(HERE / "prepare_confirmation.py"),
    }
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=confirmation.REPO_ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    freeze = {
        "schema_version": 1,
        "spdx_license_identifier": "Apache-2.0",
        "protocol_id": protocol["protocol_id"],
        "protocol_revision": protocol["protocol_revision"],
        "status": "FROZEN",
        "frozen_on": now.isoformat().replace("+00:00", "Z"),
        "git_head_at_freeze": git_head,
        **surface,
        "immutable_surface_digest": {
            "algorithm": "sha256 of canonical UTF-8 JSON over all bound surface fields",
            "sha256": canonical_sha(surface),
        },
        "scope": {
            "host": "claude",
            "measured_strategy_executions": 96,
            "codex": "OUT_OF_SCOPE",
        },
        "immutability_rule": (
            "Do not edit any bound surface after freeze. Digest drift makes the "
            "confirmation run INCONCLUSIVE and requires a new protocol revision."
        ),
    }
    write_json(freeze_path, freeze)

    authorization = {
        "protocol_id": protocol["protocol_id"],
        "host": "claude",
        "authorized_by": (
            "operator, via the coordinating Codex session, for the full-scale "
            "confirmation-v1 measured_cells run"
        ),
        "authorized_on": now.date().isoformat(),
        "scope": "measured_cells",
        "protocol_sha256": sha(protocol_path),
        "freeze_sha256": sha(freeze_path),
    }
    write_json(authorization_path, authorization)

    runner.validate_freeze(protocol, case_manifest, case_manifest_path)
    runner.load_authorization("claude")
    print(json.dumps({"freeze": freeze, "authorization": authorization}, indent=2))


if __name__ == "__main__":
    main()

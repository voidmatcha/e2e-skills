#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Adversarial smoke checks for the release-v1 read-only tool broker."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/evals/reviewer-release-tool-surface-v1.py"
SPEC = importlib.util.spec_from_file_location("release_tool_surface_v1", MODULE)
assert SPEC and SPEC.loader
SURFACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SURFACE)
PROTOCOL = json.loads((ROOT / "scripts/evals/reviewer-release-v1-protocol.json").read_text(encoding="utf-8"))
DESIGN = PROTOCOL["evaluation_surface"]


def denied(action, expected: str) -> None:
    try:
        action()
    except SURFACE.ToolSurfaceError as exc:
        assert expected in str(exc), (expected, str(exc))
    else:
        raise AssertionError(f"expected ToolSurfaceError: {expected}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="reviewer-release-tools-v1-") as raw:
        root = Path(raw)
        bundle = root / "bundle"
        source = bundle / "sources/case-001/e2e/example.spec.ts"
        helper = bundle / "sources/case-001/support/helper.ts"
        package = bundle / "sources/case-001/package.json"
        marker = root / "target-command-ran"
        source.parent.mkdir(parents=True)
        helper.parent.mkdir(parents=True)
        source.write_text("import { test } from '@playwright/test';\ntest.only('x', async () => {});\n", encoding="utf-8")
        helper.write_text("export const helper = 1;\n", encoding="utf-8")
        package.write_text(json.dumps({"scripts": {"test": f"touch {marker}"}}), encoding="utf-8")

        def reference(path: Path) -> dict[str, str]:
            return {"path": path.relative_to(bundle).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

        case = {
            "source_root": "sources/case-001",
            "source_files": [reference(source), reference(helper), reference(package)],
        }
        broker = SURFACE.ReleaseToolSurface(bundle, case, ROOT, DESIGN, root / "workspace")
        assert broker.read_staged_case_file("sources/case-001/support/helper.ts") == helper.read_bytes()
        assert broker.read_staged_skill_file("skills/e2e-reviewer/SKILL.md").startswith(b"---\n")
        assert broker.read_staged_skill_file("references/review-scope.md") == (ROOT / "skills/e2e-reviewer/references/review-scope.md").read_bytes()
        denied(lambda: broker.read_staged_case_file("sources/case-001/../../labels.json"), "normalized")
        denied(lambda: broker.read_staged_case_file("sources/case-001/.env"), "undeclared")
        denied(lambda: broker.read_staged_skill_file("scripts/evals/reviewer-release-v1-protocol.json"), "undeclared")
        poison = root / "poisoned-startup.sh"
        poison.write_text(f"touch {marker}\n", encoding="utf-8")
        prior_bash_env = os.environ.get("BASH_ENV")
        os.environ["BASH_ENV"] = str(poison)
        try:
            output = broker.run_staged_bundled_scanner()
        finally:
            if prior_bash_env is None:
                os.environ.pop("BASH_ENV", None)
            else:
                os.environ["BASH_ENV"] = prior_bash_env
        assert not marker.exists(), "scanner executed target script or inherited BASH_ENV"
        assert b"Summary:" in output and b"#7" in output
        assert [row["tool"] for row in broker.transcript] == [
            "read_staged_case_file", "read_staged_skill_file", "read_staged_skill_file", "run_staged_bundled_scanner"
        ]
        assert broker.transcript[-1]["environment"] == {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(broker.workspace / "home"),
            "TMPDIR": str(broker.workspace / "tmp"),
            "LANG": "C", "LC_ALL": "C", **SURFACE.SCANNER_ENV,
        }
        denied(lambda: broker.run_staged_bundled_scanner(timeout=1), "fixed")
        staged = broker.case_root / "sources/case-001/e2e/example.spec.ts"
        staged.write_text("changed after staging\n", encoding="utf-8")
        denied(lambda: broker.read_staged_case_file("sources/case-001/e2e/example.spec.ts"), "changed")
        denied(broker.run_staged_bundled_scanner, "changed")
        broker.scanner.write_text("#!/bin/sh\nprintf 'fake summary\\n'\n", encoding="utf-8")
        denied(broker.run_staged_bundled_scanner, "scanner changed")

        bad_digest = {**case, "source_files": [{**case["source_files"][0], "sha256": "0" * 64}, *case["source_files"][1:]]}
        denied(lambda: SURFACE.ReleaseToolSurface(bundle, bad_digest, ROOT, DESIGN, root / "bad-digest"), "digest mismatch")
        bad_environment = {**DESIGN, "scanner_environment": {**SURFACE.SCANNER_ENV, "E2E_SMELL_ALLOW_PROJECT_ESLINT": "1"}}
        denied(lambda: SURFACE.ReleaseToolSurface(bundle, case, ROOT, bad_environment, root / "bad-env"), "differs")
        bad_allowlist = {**DESIGN, "on_demand_skill_files": {**DESIGN["on_demand_skill_files"], "catalog-only": ["skills/e2e-reviewer/SKILL.md"]}}
        denied(lambda: SURFACE.ReleaseToolSurface(bundle, case, ROOT, bad_allowlist, root / "bad-allowlist"), "allowlist differs")
        denied(lambda: SURFACE.ReleaseToolSurface(bundle, case, ROOT, DESIGN, root / "bad-arm", arm="other"), "unknown")

        extra = bundle / "sources/case-001/undeclared.ts"
        extra.write_text("extra\n", encoding="utf-8")
        denied(lambda: SURFACE.ReleaseToolSurface(bundle, case, ROOT, DESIGN, root / "extra-workspace"), "exactly cover")
        extra.unlink()
        inside = bundle / "sources/case-001/injected-workspace"
        denied(lambda: SURFACE.ReleaseToolSurface(bundle, case, ROOT, DESIGN, inside), "outside the source bundle")
        assert not inside.exists(), "broker wrote into the original case before rejecting the workspace"
        source.unlink()
        source.symlink_to(helper)
        denied(lambda: SURFACE.ReleaseToolSurface(bundle, case, ROOT, DESIGN, root / "link-workspace"), "symlink")
        source.unlink()
        source.write_text("import { test } from '@playwright/test';\ntest.only('x', async () => {});\n", encoding="utf-8")
        catalog = SURFACE.ReleaseToolSurface(bundle, case, ROOT, DESIGN, root / "catalog", arm="catalog-only")
        assert list(catalog.initial_model_material()) == ["skills/e2e-reviewer/references/pattern-reference.md"]
        denied(lambda: catalog.read_staged_skill_file("skills/e2e-reviewer/references/pattern-reference.md"), "full-arm only")
        denied(catalog.run_staged_bundled_scanner, "full-arm only")
        baseline = SURFACE.ReleaseToolSurface(bundle, case, ROOT, DESIGN, root / "baseline", arm="no-skill")
        assert baseline.initial_model_material() == {}
        denied(lambda: baseline.read_staged_skill_file("skills/e2e-reviewer/SKILL.md"), "full-arm only")
        denied(baseline.run_staged_bundled_scanner, "full-arm only")
        cypress = bundle / "sources/case-002/cypress/e2e/example.cy.ts"
        cypress.parent.mkdir(parents=True)
        cypress.write_text("it('waits', () => { cy.wait(100); });\n", encoding="utf-8")
        cypress_case = {"source_root": "sources/case-002", "source_files": [reference(cypress)]}
        cypress_broker = SURFACE.ReleaseToolSurface(bundle, cypress_case, ROOT, DESIGN, root / "cypress", arm="full")
        cypress_output = cypress_broker.run_staged_bundled_scanner()
        assert b"#9b" in cypress_output
        malformed = [
            b"not a scanner report\nSummary: 0 total hit(s)\n",
            cypress_output + b"\ntrailing junk\n",
            cypress_output.replace(b"--- Tier 3:", b"--- Tier 2:"),
        ]
        for output in malformed:
            assert not SURFACE.scanner_report_complete(output)
            with patch.object(SURFACE.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output, b"")):
                denied(cypress_broker.run_staged_bundled_scanner, "valid Tier 3")

        def mutate_skill(*_args, **_kwargs):
            staged_skill = cypress_broker.skill_root / "skills/e2e-reviewer/SKILL.md"
            staged_skill.write_text("changed during scanner call\n", encoding="utf-8")
            return subprocess.CompletedProcess([], 0, cypress_output, b"")

        with patch.object(SURFACE.subprocess, "run", side_effect=mutate_skill):
            denied(cypress_broker.run_staged_bundled_scanner, "staged skill changed")

    print("reviewer release tool surface v1: pass (both frameworks; snapshot, allowlist, scanner, mutation and symlink guards)")


if __name__ == "__main__":
    main()

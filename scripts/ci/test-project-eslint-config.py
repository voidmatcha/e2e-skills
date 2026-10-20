#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Opt-in integration check using real, separately installed ESLint packages.

No downloads occur here. Install the exact PINS in an external directory with
``npm install --prefix DIR --ignore-scripts --no-audit --no-fund --save-exact``
and pass ``--deps DIR --output /external/path/results.json``. This intentionally
is not part of dependency-free local CI. Only generated temporary fixtures are
trusted for project ESLint execution.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import tempfile


PINS = {
    "eslint": "10.8.0",
    "@typescript-eslint/parser": "8.65.0",
    "typescript": "6.0.3",
    "eslint-plugin-playwright": "2.11.0",
    "eslint-plugin-cypress": "6.4.3",
    "eslint-plugin-mocha": "12.0.1",
}
WAIT_RULES = ("playwright/no-wait-for-timeout", "cypress/no-unnecessary-waiting")
FOCUS_RULES = ("playwright/no-focused-test", "mocha/no-exclusive-tests")
ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deps", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scanner", type=Path, default=ROOT / "skills/e2e-reviewer/scripts/scan.sh")
    parser.add_argument("--node", type=Path, help="Trusted runtime, overriding E2E_SKILLS_NODE_BIN")
    args = parser.parse_args()
    trusted_node = runpy.run_path(str(Path(__file__).with_name("test-eslint-import-resolution.py")))["trusted_node_executable"]
    try:
        node = trusted_node(args.node)
    except ValueError as error:
        parser.error(str(error))
    modules = args.deps.resolve() / "node_modules"
    versions = {
        name: json.loads((modules / name / "package.json").read_text())["version"]
        for name in PINS
    }
    if versions != PINS:
        parser.error(f"Expected exact real package versions {PINS}; got {versions}")
    scanner = args.scanner.resolve()
    scanner_sha256 = hashlib.sha256(scanner.read_bytes()).hexdigest()
    results = []
    with tempfile.TemporaryDirectory(prefix="e2e-real-eslint-") as temporary:
        base = Path(temporary)
        for case in ("baseline", "default-disabled", "flat-mjs", "flat-js", "flat-cjs", "legacy"):
            project = base / case
            project.mkdir()
            (project / ".git").mkdir()
            (project / "node_modules").symlink_to(modules, target_is_directory=True)
            (project / "tests").mkdir()
            (project / "cypress/e2e").mkdir(parents=True)
            (project / "package.json").write_text('{"private":true}\n')
            (project / "tests/local.spec.js").write_text(
                "import { test, expect } from '@playwright/test';\n"
                "test.only('real config', async ({ page }) => {\n"
                "  await page.waitForTimeout(123);\n"
                "  await expect(page.getByRole('status')).toBeVisible();\n"
                "});\n"
            )
            (project / "cypress/e2e/local.cy.js").write_text(
                "describe('real config', () => {\n"
                "  it.only('wait', () => {\n"
                "    cy.visit('/');\n"
                "    cy.wait(123);\n"
                "    cy.get('[data-cy=status]').should('be.visible');\n"
                "  });\n"
                "});\n"
            )
            marker = project / "config-executed"
            entries = [
                {"files": ["tests/**"], "rules": {WAIT_RULES[0]: "off"}},
                {"files": ["cypress/e2e/**"], "rules": {WAIT_RULES[1]: "off"}},
            ]
            if case.startswith("flat-") or case == "default-disabled":
                extension = case.split("-")[-1] if case.startswith("flat-") else "mjs"
                header = (
                    "import fs from 'node:fs';\n" if extension == "mjs"
                    else "const fs = require('node:fs');\n"
                )
                export = "export default " if extension == "mjs" else "module.exports = "
                # Cover array and single-object exports, with project-relative globs.
                config = entries if extension != "cjs" else {
                    "files": ["tests/**", "cypress/e2e/**"],
                    "rules": {rule: "off" for rule in WAIT_RULES},
                }
                (project / f"eslint.config.{extension}").write_text(
                    header + f"fs.writeFileSync({json.dumps(str(marker))}, 'loaded');\n"
                    + export + json.dumps(config) + ";\n"
                )
            elif case == "legacy":
                (project / ".eslintrc.json").write_text(json.dumps({
                    "rules": {rule: "off" for rule in WAIT_RULES},
                }))
            env = dict(os.environ)
            env.update({
                "E2E_SMELL_ALLOW_PROJECT_ESLINT": "0" if case == "default-disabled" else "1",
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_DISABLE_AST_GREP": "1",
                "E2E_SMELL_NODE_BIN": str(node),
            })
            proc = subprocess.run(
                ["/bin/bash", "-p", str(scanner), str(project)],
                env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=120, check=False,
            )
            output = proc.stdout
            # Only ESLint stylish diagnostic rows qualify; Tier 2/3 summaries
            # cannot establish that the real plugin ran or obeyed a config.
            rules = set(re.findall(r"^\s+\d+:\d+\s+(?:error|warning)\s+.*?\s+([\w-]+/[\w-]+)\s*$", output, re.M))
            checks = {"focused_exit": proc.returncode == 1, "summary": "Summary:" in output}
            if case == "default-disabled":
                checks.update({"config_not_executed": not marker.exists(),
                               "tier1_disabled": "Tier 1 disabled by default" in output,
                               "no_tier1_diagnostics": not rules})
            else:
                checks.update({f"real_{plugin}_ran":
                    f"running eslint-plugin-{plugin} (locally installed)" in output
                    for plugin in ("playwright", "cypress")})
                checks["no_crash_or_skip"] = "crashed or unusable" not in output and "skipping Tier 1" not in output
                for rule in FOCUS_RULES:
                    checks[f"baseline_retained:{rule}"] = rule in rules
                disabled = case.startswith("flat-")
                for plugin, rule in zip(("playwright", "cypress"), WAIT_RULES):
                    checks[f"project_wait_policy:{plugin}"] = checks[f"real_{plugin}_ran"] and ((rule not in rules) if disabled else (rule in rules))
                if disabled:
                    checks["config_executed"] = marker.exists()
                    checks["independent_tier3_wait_retained"] = "#9 Playwright hard-coded sleep" in output and "#9b Cypress hard-coded sleep" in output
                if case == "legacy":
                    checks["legacy_fallback_explained"] = "legacy .eslintrc" in output and "NOT honored" in output
            passed = all(checks.values())
            results.append({"case": case, "pass": passed, "checks": checks,
                            "exit_code": proc.returncode, "tier1_rules": sorted(rules), "output": output})
            print(f"{'PASS' if passed else 'FAIL'} {case}: {checks}", flush=True)
    report = {"pass": all(result["pass"] for result in results), "versions": versions,
              "node": subprocess.check_output([str(node), "--version"], text=True).strip(),
              "node_executable": str(node),
              "scanner": str(scanner), "scanner_sha256": scanner_sha256,
              "scanner_unchanged_during_run": hashlib.sha256(scanner.read_bytes()).hexdigest() == scanner_sha256,
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "limitations": ["Only pinned versions, JavaScript fixtures and a local install are tested.",
                              "No network fallback, browser execution or legacy config import is tested."],
              "results": results}
    report["pass"] = report["pass"] and report["scanner_unchanged_during_run"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

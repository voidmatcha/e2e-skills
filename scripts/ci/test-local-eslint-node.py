#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Local ESLint contracts through a copied skill's Node launcher and runtime.

The generated runtime is copied at invocation; this suite never rebuilds it,
downloads dependencies, or creates checkout node_modules. Project ESLint is an
API mock, so these are consumer/trust tests, not an ESLint implementation test.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TRUST = ("--project-eslint", "--trust-project")
SECRET = "LOCAL_ESLINT_PRIVATE_SENTINEL_7bd31"


def digest_tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class LocalEslintNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install_temp = tempfile.TemporaryDirectory(prefix="eslint-node-installed-")
        cls.scripts = Path(cls.install_temp.name).resolve() / "e2e-reviewer/scripts"
        cls.scripts.mkdir(parents=True)
        cls.launcher = cls.scripts / "scan.sh"
        shutil.copy2(ROOT / "scripts/dev/scanner-launcher.sh", cls.launcher)
        shutil.copytree(ROOT / "skills/e2e-reviewer/scripts/scanner", cls.scripts / "scanner")
        cls.installed_bytes = digest_tree(cls.scripts)
        if any(cls.scripts.rglob("node_modules")):
            raise AssertionError("installed runtime must not resolve checkout dependencies")
        print("local-eslint-node runtime manifest sha256:",
              cls.installed_bytes["scanner/manifest.json"], flush=True)

    @classmethod
    def tearDownClass(cls):
        try:
            if digest_tree(cls.scripts) != cls.installed_bytes:
                raise AssertionError("installed scanner changed during the suite")
        finally:
            cls.install_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="eslint-node-project-")
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        self.receipt = self.base / "receipt.json"
        self.config_marker = self.base / "config-executed"
        self.module_marker = self.base / "module-executed"
        self.cli_marker = self.base / "unexpected-cli-executed"
        self.inputs = {}
        self.put("package.json", '{"private":true}\n')
        self.put("tests/local.spec.ts", "import { expect, test } from '@playwright/test';\n"
                 "test('local', async ({ page }) => {\n"
                 "  const status = page.getByRole('status');\n"
                 "  expect(status).toBeTruthy();\n});\n")
        self.put("tests/justified.spec.ts", "import { expect, test } from '@playwright/test';\n"
                 "test('justified', async ({ page }) => {\n"
                 "  const status = page.getByRole('status');\n"
                 "  // JUSTIFIED: the wrapper consumes this assertion promise externally\n"
                 "  expect(status).toBeTruthy();\n});\n")
        self.put("tests/unit.test.ts", "import { expect, test } from 'vitest';\n"
                 "test.only('unit', () => { expect(true).toBe(true); });\n")
        self.put("cypress/e2e/local.cy.js", "describe('local', () => {\n"
                 "  it.only('local', () => {\n"
                 "    cy.visit('/');\n"
                 "    cy.get('[data-cy=submit]').should('be.visible');\n  });\n});\n")
        self.write_config()
        self.put("node_modules/eslint/package.json",
                 json.dumps({"name": "eslint", "version": "9.39.1", "main": "index.cjs"}))
        self.write_engine()
        # No project CLI/package manager may be used by the Node API path.
        for name in ("node_modules/.bin/eslint", "bin/npx"):
            file = self.put(name, "#!/bin/sh\nprintf unexpected > " +
                            "'" + str(self.cli_marker) + "'\nexit 99\n")
            file.chmod(0o755)

    def tearDown(self):
        try:
            for file, expected in self.inputs.items():
                self.assertEqual(file.read_bytes(), expected, "reviewed project input changed")
            self.assertFalse(self.cli_marker.exists(), "project CLI or npx executed")
        finally:
            self.temp.cleanup()

    def put(self, name, text):
        file = self.project / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        self.inputs[file] = file.read_bytes()
        return file

    def write_config(self, body="module.exports = [];"):
        self.put("eslint.config.cjs", "require('node:fs').writeFileSync(" +
                 json.dumps(str(self.config_marker)) + ", 'executed');\n" + body + "\n")

    def write_engine(self, body=None, *, mapped=False):
        if body is None:
            body = "return files.map(filePath => ({filePath, messages: []}));"
        if mapped:
            body = """
return files.map(filePath => {
  const name = path.basename(filePath);
  const line = name === 'local.cy.js' ? 2 : name === 'justified.spec.ts' ? 5 : 4;
  const ruleId = name === 'local.cy.js' ? 'mocha/no-exclusive-tests' : 'playwright/no-unnecessary-assertions';
  return {filePath, messages: ['local.cy.js','local.spec.ts','justified.spec.ts'].includes(name)
    ? [{ruleId, severity:1, line, column:3, message:PRIVATE, source:PRIVATE, fix:{text:PRIVATE}}] : []};
});
"""
        self.put("node_modules/eslint/index.cjs", "\n".join([
            "const fs=require('node:fs'), path=require('node:path');",
            "const PRIVATE=" + json.dumps(SECRET) + ";",
            "fs.writeFileSync(" + json.dumps(str(self.module_marker)) + ", 'executed');",
            "exports.ESLint=class {",
            "constructor(options) { this.options=options; require(options.overrideConfigFile); }",
            "async calculateConfigForFile() { return {rules: {}}; }",
            "async isPathIgnored() { return false; }",
            "async lintFiles(files) {",
            "fs.writeFileSync(" + json.dumps(str(self.receipt)) + ", JSON.stringify({files,options:this.options,cwd:process.cwd(),secret:process.env.E2E_SCANNER_TEST_SECRET??null,nodeOptions:process.env.NODE_OPTIONS??null,nodePath:process.env.NODE_PATH??null,environment:Object.fromEntries(['HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR','TMPDIR','TMP','TEMP','npm_config_userconfig','CI','NO_COLOR'].map(key=>[key,process.env[key]]))}));",
            body, "}};", "",
        ]))

    def run_scan(self, *args, expected=1, root=None, text=False, environment=None):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("E2E_SMELL_") and key not in
               ("NODE_OPTIONS", "NODE_PATH", "BASH_ENV", "ENV")}
        env.update({"E2E_SCANNER_TEST_SECRET": SECRET,
                    "PATH": str(self.project / "bin") + os.pathsep + env.get("PATH", "")})
        env.update(environment or {})
        result = subprocess.run(
            ["/bin/bash", "-p", str(self.launcher), str(root or self.project),
             "--format", "text" if text else "json", *args],
            cwd=self.project, env=env, capture_output=True, text=True, timeout=45)
        self.assertNotIn(SECRET, result.stdout + result.stderr, "project secrets leaked")
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result if text else json.loads(result.stdout)

    def assert_scope_receipt(self, expected):
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(set(receipt["files"]), {str(self.project / p) for p in expected},
                         "ESLint must receive E2E-scoped files only")
        self.assertEqual(receipt["cwd"], str(self.project))
        self.assertEqual(receipt["options"]["cwd"], str(self.project))
        for field in ("secret", "nodeOptions", "nodePath"):
            self.assertIsNone(receipt[field], field)
        environment = receipt["environment"]
        private_home = Path(environment["HOME"])
        self.assertNotEqual(str(private_home), os.environ.get("HOME"))
        for field in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
            self.assertEqual(Path(environment[field]).parent, private_home.parent, field)
        self.assertFalse(private_home.parent.exists(), "owned worker environment must be cleaned up")
        self.assertEqual(environment["npm_config_userconfig"], "/dev/null")
        self.assertEqual(environment["CI"], "1")
        self.assertEqual(environment["NO_COLOR"], "1")

    def test_default_disabled_retains_static_findings_without_execution(self):
        report = self.run_scan()
        self.assertTrue(report["execution"]["complete"])
        self.assertFalse(report["projectEslint"]["executed"])
        self.assertFalse(report["configurationAnalysis"]["effectiveConfiguration"])
        self.assertFalse(report["configurationAnalysis"]["runnerSelectionApplied"])
        self.assertTrue(report["configurationAnalysis"]["configurations"])
        self.assertFalse(self.config_marker.exists())
        self.assertFalse(self.module_marker.exists())
        self.assertTrue(any(f["patternId"] == "#7" and f["disposition"] == "confirmed"
                            for f in report["findings"]))

    def test_paired_opt_in_and_explicit_retired_option_migration(self):
        for args, environment in [(("--project-eslint",), {}), (("--trust-project",), {}),
                                  ((), {"E2E_SMELL_ALLOW_PROJECT_ESLINT": "yes"}),
                                  ((), {"E2E_SMELL_ALLOW_PROJECT_ESLINT": "1"}),
                                  ((), {"E2E_SMELL_NO_ESLINT_DOWNLOAD": "invalid"}),
                                  ((), {"E2E_SMELL_NO_AST_GREP_DOWNLOAD": "invalid"})]:
            with self.subTest(args=args, environment=environment):
                result = self.run_scan(*args, expected=2, text=True, environment=environment)
                self.assertFalse(any(line.startswith("Summary:") for line in result.stdout.splitlines()))
                self.assertFalse(self.module_marker.exists())
                self.assertFalse(self.config_marker.exists())

    def test_trusted_api_scope_cwd_and_environment(self):
        report = self.run_scan(*TRUST)
        self.assertTrue(report["execution"]["complete"])
        self.assertTrue(report["project"]["configurationExecuted"])
        self.assertTrue(self.config_marker.exists())
        self.assert_scope_receipt(["tests/local.spec.ts", "tests/justified.spec.ts",
                                   "cypress/e2e/local.cy.js"])

    def test_warning_mappings_same_location_dedupe_and_justified(self):
        self.write_engine(mapped=True)
        report = self.run_scan(*TRUST)
        self.assertTrue(report["execution"]["complete"])
        self.assertEqual({key: report["counts"][key] for key in
                          ("total", "p0", "p1p2", "triage", "p0Candidate")},
                         {"total": 3, "p0": 2, "p1p2": 0, "triage": 1, "p0Candidate": 1})
        self.assertEqual(len(report["findings"]), 3)
        self.assertEqual({(f["patternId"], f["origin"]) for f in report["findings"]
                          if f["disposition"] == "confirmed"},
                         {("#7", "eslint"), ("#4f", "eslint")})
        self.assertEqual(len(report["duplicates"]), 3)
        for duplicate in report["duplicates"]:
            self.assertEqual(tuple(duplicate["finding"][key] for key in ("file", "line", "patternId")),
                             tuple(duplicate["retained"][key] for key in ("file", "line", "patternId")))
        justified = [f for f in report["findings"] if f["file"].endswith("/justified.spec.ts")]
        self.assertEqual(len(justified), 1)
        self.assertEqual(justified[0]["line"], 5)
        self.assertEqual(justified[0]["disposition"], "justified-review")
        result = self.run_scan(*TRUST, text=True)
        self.assertIn("Summary: 3 total hit(s), 2 P0, 0 P1/P2 heuristic, 1 LLM-triage, 1 P0 candidate",
                      result.stdout)

    def test_nested_root_excludes_cypress_and_foreign_tests(self):
        self.write_engine(mapped=True)
        report = self.run_scan(*TRUST, root=self.project / "tests")
        self.assertTrue(report["execution"]["complete"])
        self.assert_scope_receipt(["tests/local.spec.ts", "tests/justified.spec.ts"])
        self.assertEqual({key: report["counts"][key] for key in
                          ("total", "p0", "p1p2", "triage", "p0Candidate")},
                         {"total": 2, "p0": 1, "p1p2": 0, "triage": 1, "p0Candidate": 1})
        result = self.run_scan(*TRUST, root=self.project / "tests", text=True)
        self.assertIn("Summary: 2 total hit(s), 1 P0, 0 P1/P2 heuristic, 1 LLM-triage, 1 P0 candidate",
                      result.stdout)

    def test_config_api_and_foreign_rule_failures_are_incomplete(self):
        for failure in ("config", "api", "foreign-rule"):
            with self.subTest(failure=failure):
                self.write_config("throw new Error(" + json.dumps(SECRET) + ");"
                                  if failure == "config" else "module.exports = [];")
                if failure == "api":
                    self.write_engine("throw new Error(PRIVATE);")
                elif failure == "foreign-rule":
                    self.write_engine("return files.map(filePath=>({filePath,messages:[{ruleId:'cypress/no-unnecessary-assertions',severity:1,line:2,column:3,message:PRIVATE}]}));")
                else:
                    self.write_engine()
                report = self.run_scan(*TRUST, "--fail-on", "none", expected=2)
                self.assertFalse(report["execution"]["complete"])
                self.assertTrue(any(d["detector"] == "projectEslint"
                                    for d in report["execution"]["diagnostics"]))
                result = self.run_scan(*TRUST, "--fail-on", "none", expected=2, text=True)
                self.assertFalse(any(line.startswith("Summary:") for line in result.stdout.splitlines()))

    def test_hostile_output_is_bounded_and_never_leaks(self):
        # Exceed the current public worker's 16 MiB ceiling, synchronously, so
        # completion cannot race ahead of buffered writes. No legacy limit knob.
        self.write_engine("const chunk=PRIVATE+'x'.repeat(65536); for(let i=0;i<300;i++)fs.writeSync(1,chunk); return files.map(filePath=>({filePath,messages:[]}));")
        report = self.run_scan(*TRUST, "--fail-on", "none", expected=2)
        self.assertFalse(report["execution"]["complete"])
        self.assertTrue(any(d["code"] == "eslint-output-limit"
                            for d in report["execution"]["diagnostics"]))
        result = self.run_scan(*TRUST, "--fail-on", "none", expected=2, text=True)
        self.assertLess(len(result.stdout) + len(result.stderr), 65536)
        self.assertFalse(any(line.startswith("Summary:") for line in result.stdout.splitlines()))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The CI-only frozen exception cannot hide changed or additional test source."""
from __future__ import annotations

import importlib.util
import json
import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / "scripts/ci/lib/self-scan-view.py"
SPEC = importlib.util.spec_from_file_location("self_scan_view", HELPER_PATH)
assert SPEC and SPEC.loader
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="self-scan-view-tests-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.source = self.base / "source"
        self.source.mkdir()
        self.fixture = self.source / HELPER.FROZEN_PATH
        self.fixture.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / HELPER.FROZEN_PATH, self.fixture)
        self.fixture.chmod(HELPER.FROZEN_MODE)
        for name in HELPER.REQUIRED:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("identity marker\n")
        (self.source / ".git").mkdir()
        (self.source / ".git/HEAD").write_text("private source metadata\n")
        self.view = self.base / "view"

    def add_file(self, name, content, mode=0o644):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(mode)
        return path

    def test_every_entry_is_copied_byte_for_byte_with_mode_and_only_exact_exception(self):
        self.add_file("scripts/untracked.spec.ts", "test.only('must survive', () => {});", 0o751)
        self.add_file("skills/.hidden/data", "untracked hidden bytes\n", 0o640)
        self.add_file("support/root-fixture.ts", "export const test = other;\n")
        self.add_file("package.json", '{"type":"module"}\n')
        self.add_file("scripts/node_modules/fixture/raw.bin", "not silently skipped\n")
        self.add_file("scripts/__pycache__/source.spec.ts", "not silently skipped\n")
        (self.source / "scripts/empty").mkdir(mode=0o750)
        original = HELPER.inventory(self.source)
        recorded = HELPER.create_view(self.source, self.view)
        self.assertEqual(original, recorded)
        self.assertEqual(HELPER.inventory(self.source), original)
        self.assertEqual(HELPER.inventory(self.view),
                         {key: value for key, value in original.items() if key != HELPER.FROZEN_PATH})
        # Independently enumerate actual files, so a shared inventory/copy bug
        # cannot make an omitted untracked/root/hidden file appear equivalent.
        expected_files = {path.relative_to(self.source).as_posix(): path
                          for path in self.source.rglob("*") if path.is_file()
                          and ".git" not in path.relative_to(self.source).parts
                          and path != self.fixture}
        actual_files = {path.relative_to(self.view).as_posix(): path
                        for path in self.view.rglob("*") if path.is_file()}
        self.assertEqual(set(actual_files), set(expected_files))
        for name, path in expected_files.items():
            self.assertEqual(actual_files[name].read_bytes(), path.read_bytes(), name)
            self.assertEqual(actual_files[name].stat().st_mode & 0o7777,
                             path.stat().st_mode & 0o7777, name)
        self.assertEqual((self.view / "scripts/empty").stat().st_mode & 0o7777, 0o750)
        self.assertFalse((self.view / HELPER.FROZEN_PATH).exists())
        self.assertEqual(list((self.view / ".git").iterdir()), [])
        self.assertEqual((self.source / ".git/HEAD").read_text(), "private source metadata\n")

    def test_missing_changed_mode_and_changed_bytes_refuse_exception_before_scan(self):
        original = self.fixture.read_bytes()
        for failure in ("missing", "bytes", "mode"):
            with self.subTest(failure=failure):
                self.fixture.write_bytes(original)
                self.fixture.chmod(0o644)
                if failure == "missing":
                    self.fixture.unlink()
                elif failure == "bytes":
                    self.fixture.write_bytes(original + b"\n// altered historical evidence\n")
                else:
                    self.fixture.chmod(0o600)
                with patch.object(HELPER, "scan") as scanner:
                    with self.assertRaisesRegex(HELPER.ViewError, "frozen control"):
                        HELPER.create_view(self.source, self.view)
                    scanner.assert_not_called()
                self.assertFalse(self.view.exists())

    def test_symlinks_and_special_files_are_rejected_instead_of_omitted(self):
        outside = self.base / "outside.spec.ts"
        outside.write_text("test.only('outside', () => {});\n")
        cases = (HELPER.FROZEN_PATH, "scripts/untracked.spec.ts", "support", ".git")
        for name in cases:
            with self.subTest(name=name):
                path = self.source / name
                saved = path.read_bytes() if path.is_file() else None
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()
                path.symlink_to(outside)
                with self.assertRaises(HELPER.ViewError):
                    HELPER.create_view(self.source, self.view)
                self.assertFalse(self.view.exists())
                path.unlink()
                if saved is not None:
                    path.write_bytes(saved)
                    path.chmod(0o644)
        fifo = self.source / "scripts/input.spec.ts"
        os.mkfifo(fifo)
        with self.assertRaises(HELPER.ViewError):
            HELPER.create_view(self.source, self.view)
        self.assertFalse(self.view.exists())

    def test_source_or_view_mutation_cannot_pass_verification(self):
        extra = self.add_file("scripts/extra.spec.ts", "ordinary source\n")
        original = HELPER.create_view(self.source, self.view)
        extra.write_text("changed source\n")
        with self.assertRaisesRegex(HELPER.ViewError, "source entries"):
            HELPER.verify_view(self.source, self.view, original)
        extra.write_text("ordinary source\n")
        (self.view / "scripts/extra.spec.ts").unlink()
        with self.assertRaisesRegex(HELPER.ViewError, "view entries"):
            HELPER.verify_view(self.source, self.view, original)

    def test_in_source_existing_or_ancestor_destination_refused(self):
        for destination in (self.source / "view", self.source, self.base):
            with self.subTest(destination=destination):
                with self.assertRaises(HELPER.ViewError):
                    HELPER.create_view(self.source, destination)

    def control_report(self):
        file = str(self.fixture)
        gaps = [("actions", "import-unpinned", None), ("pageReads", "import-unpinned", 1517),
                ("accessibleNames", "import-unpinned", 543),
                ("conditionalAssertions", "provenance-unsupported", 1801),
                ("conditionalAssertions", "import-unpinned", 1920),
                ("conditionalAssertions", "import-unpinned", 2115)]
        return {
            "schema": "e2e-skills-node-scan-v1", "status": "INCOMPLETE", "scope": "static-review",
            "failOn": "p0-candidate", "files": 1, "coverage": {"complete": False},
            "compatibility": {"contract": "source-review-v1", "status": "development", "referenceLegacyCallVariants": 69},
            "review": {"required": True, "candidates": 2, "obligations": []},
            "execution": {"complete": False, "exitCode": 2,
                          "incomplete": [f"analysis incomplete: {file}: {detector} could not establish its contract"
                                         + (f" at offset {start}" if start is not None else "")
                                         for detector, _, start in gaps],
                          "diagnostics": [{"code": code, "detector": detector, "file": file,
                                           **({"start": start} if start is not None else {})}
                                          for detector, code, start in gaps]},
            "counts": {"total": 2, "p0": 0, "p1p2": 0, "triage": 2, "p0Candidate": 2, "ast": 2, "confirmed": 0},
            "findings": [{"patternId": pattern, "severity": "P0", "disposition": "candidate", "origin": "ast",
                          "file": file, "line": line, "column": column, "start": start, "end": end,
                          "evidence": {"kind": "unresolved-fixture",
                                       "requirements": ["verify-runtime-binding", "verify-required-test-outcome"]}}
                         for pattern, line, column, start, end in [("#5a", 25, 5, 1655, 2185), ("#3", 35, 34, 2233, 2270)]],
            "suppressed": [], "duplicates": [], "projectEslint": {"requested": False, "executed": False},
            "configurationAnalysis": {
                "schema": "node-configuration-context-v1", "status": "UNAVAILABLE",
                "projectRoot": str(self.source), "effectiveConfiguration": False,
                "runnerSelectionApplied": False, "configurations": [],
                "unknowns": [{"code": "CONFIG_ROOT_NOT_FOUND"}],
                "ruleComparison": {
                    "relationship": "OVERLAPPING_SLICES_NOT_EQUIVALENT_COVERAGE",
                    "mappedRules": [], "scannerSlicesWithoutMappedEslintRule": [],
                    "scannerRulesDisabled": False,
                    "effectiveRuleStates": "projectEslint.effectiveConfiguration.files",
                },
            },
        }

    def test_unknown_original_scan_outcomes_fail_closed(self):
        valid = self.control_report()
        verify = lambda report, code=2: HELPER.verify_original_candidates(
            self.source, subprocess.CompletedProcess([], code, json.dumps(report)))
        verify(valid)
        mutations = [
            ("schema", "e2e-skills-node-bounded-v1"), ("status", "COMPLETE"), ("files", 2),
            ("files", True), ("failOn", "none"), ("coverage", {"complete": True}),
            ("review", {"required": False, "candidates": 2, "obligations": []}),
            ("projectEslint", {"requested": True, "executed": True}),
            ("suppressed", [valid["findings"][0]]), ("findings", valid["findings"][:1]),
            ("errors", ["scanner failure"]),
        ]
        for field, value in mutations:
            changed = copy.deepcopy(valid)
            changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(HELPER.ViewError):
                verify(changed)
        for field, value in [("file", str(self.fixture.with_name("copied-notepad.spec.cjs"))),
                             ("line", 26), ("start", 1656), ("end", 2186), ("patternId", "#7"),
                             ("severity", "P1"), ("disposition", "confirmed"), ("evidence", {})]:
            changed = copy.deepcopy(valid)
            changed["findings"][0][field] = value
            with self.subTest(finding=field), self.assertRaises(HELPER.ViewError):
                verify(changed)
        for field, value in [("code", "parse-invalid"), ("code", "scope-incomplete"),
                             ("file", str(self.fixture.with_name("other.spec.ts"))),
                             ("detector", "other"), ("start", 123)]:
            changed = copy.deepcopy(valid)
            changed["execution"]["diagnostics"][0][field] = value
            with self.subTest(diagnostic=field), self.assertRaises(HELPER.ViewError):
                verify(changed)
        for change in ("missing-gap", "extra-gap", "complete", "exit", "empty-reasons", "fake-count"):
            changed = copy.deepcopy(valid)
            if change == "missing-gap": changed["execution"]["diagnostics"].pop()
            elif change == "extra-gap": changed["execution"]["diagnostics"].append({"code": "parse-invalid"})
            elif change == "complete": changed["execution"]["complete"] = True
            elif change == "exit": changed["execution"]["exitCode"] = 0
            elif change == "empty-reasons": changed["execution"]["incomplete"] = []
            else: changed["counts"]["p0"] = 1
            with self.subTest(change=change), self.assertRaises(HELPER.ViewError):
                verify(changed)
        for code in (0, 1, -9):
            with self.subTest(code=code), self.assertRaises(HELPER.ViewError):
                verify(valid, code)
        for field, value in [
            ("schema", "unknown"), ("status", "COMPLETE"), ("projectRoot", "/other"),
            ("effectiveConfiguration", True), ("effectiveConfiguration", 0),
            ("runnerSelectionApplied", True), ("runnerSelectionApplied", 0),
            ("configurations", {}), ("configurations", [None]),
            ("unknowns", None), ("unknowns", ["unstructured"]), ("ruleComparison", None),
        ]:
            changed = copy.deepcopy(valid)
            changed["configurationAnalysis"][field] = value
            with self.subTest(configuration=field, value=value), self.assertRaises(HELPER.ViewError):
                verify(changed)
        for field, value in [
            ("scannerRulesDisabled", True), ("scannerRulesDisabled", 0),
            ("relationship", "EQUIVALENT"), ("effectiveRuleStates", "guessed"),
            ("mappedRules", None), ("mappedRules", [False]),
            ("scannerSlicesWithoutMappedEslintRule", {}),
            ("scannerSlicesWithoutMappedEslintRule", [None]),
        ]:
            changed = copy.deepcopy(valid)
            changed["configurationAnalysis"]["ruleComparison"][field] = value
            with self.subTest(comparison=field, value=value), self.assertRaises(HELPER.ViewError):
                verify(changed)
        for value in (None, [], False):
            changed = copy.deepcopy(valid)
            changed["configurationAnalysis"] = value
            with self.subTest(configuration=value), self.assertRaises(HELPER.ViewError):
                verify(changed)
        changed = copy.deepcopy(valid)
        del changed["configurationAnalysis"]
        with self.assertRaises(HELPER.ViewError):
            verify(changed)
        for output in ("", "null", "[]", "{}", json.dumps(valid) + "error: failed",
                       json.dumps(valid) + json.dumps(valid), '{"files":1,"files":1}',
                       '{"files":NaN}'):
            with self.subTest(output=output), self.assertRaises(HELPER.ViewError):
                HELPER.verify_original_candidates(self.source, subprocess.CompletedProcess([], 2, output))

    def test_negative_control_rechecks_original_bytes_mode_and_exact_path(self):
        report = subprocess.CompletedProcess([], 2, json.dumps(self.control_report()))
        original = self.fixture.read_bytes()
        identity = HELPER.describe_file(self.fixture)
        with patch.object(HELPER, "describe_file", side_effect=[identity, {**identity, "mode": 0o600}]):
            with self.assertRaisesRegex(HELPER.ViewError, "changed during report validation"):
                HELPER.verify_original_candidates(self.source, report)
        self.fixture.write_bytes(original + b"\n")
        with self.assertRaises(HELPER.ViewError):
            HELPER.verify_original_candidates(self.source, report)
        self.fixture.write_bytes(original)
        self.fixture.chmod(0o600)
        with self.assertRaises(HELPER.ViewError):
            HELPER.verify_original_candidates(self.source, report)
        self.fixture.chmod(0o644)
        copied = self.fixture.with_name("copied-notepad.spec.cjs")
        self.fixture.rename(copied)
        with self.assertRaises(OSError):
            HELPER.verify_original_candidates(self.source, report)
        self.fixture.symlink_to(copied)
        with self.assertRaises(OSError):
            HELPER.verify_original_candidates(self.source, report)

    def test_only_pinned_negative_control_requests_json(self):
        with patch.object(HELPER.subprocess, "run") as invoke:
            HELPER.scan(self.source, HELPER.FROZEN_PATH, capture=True, json_report=True)
            self.assertEqual(invoke.call_args.args[0], ["/bin/bash", "-p", str(self.source / HELPER.SCANNER),
                                                       HELPER.FROZEN_PATH, "--format", "json"])
            HELPER.scan(self.source, "scripts", capture=True)
            self.assertEqual(invoke.call_args.args[0], ["/bin/bash", "-p", str(self.source / HELPER.SCANNER), "scripts"])

    def test_clean_gate_requires_complete_consistent_summary_and_no_hidden_p0(self):
        clean = ("Node source scan (canonical report view)\n"
                 "Coverage: BOUNDED; discovery: COMPLETE.\n"
                 "AST-origin total: 0 hit(s); retained findings, not ast-grep execution.\n"
                 "Summary: 0 total hit(s), 0 P0, 0 P1/P2 heuristic, 0 LLM-triage, 0 P0 candidate; 0 AST-origin hit(s), canonical retained findings.\n")
        self.assertEqual(HELPER.verified_counts(subprocess.CompletedProcess([], 0, clean)), (0, 0, 0, 0, 0, 0))
        for code, output in ((2, clean), (0, ""), (0, clean + clean),
                             (0, clean.replace("discovery: COMPLETE", "discovery: INCOMPLETE")),
                             (0, clean + "[P0][CONFIRMED] #7 Static finding (1 hit)\n"),
                             (0, clean + "[P0?][LLM-TRIAGE] #3 Static candidate (1 hit)\n"),
                             (0, clean.replace("AST-origin total", "ast-grep total"))):
            with self.subTest(code=code, output=output):
                with self.assertRaises(HELPER.ViewError):
                    HELPER.verified_counts(subprocess.CompletedProcess([], code, output))

    def test_actual_scanner_keeps_original_candidates_other_path_and_new_same_parent_p0(self):
        # Exercise actual product scanner, not a stub. Root Git-boundary identity
        # must also preserve its existing intentional-fixture exclusions.
        shutil.rmtree(self.source / "skills")
        shutil.copytree(ROOT / "skills/e2e-reviewer", self.source / "skills/e2e-reviewer")
        frozen_copy = self.fixture.with_name("copied-notepad.spec.cjs")
        shutil.copyfile(self.fixture, frozen_copy)
        self.add_file(str(self.fixture.parent.relative_to(self.source) / "new.spec.ts"),
                      "import { test, expect } from '@playwright/test';\n"
                      "test.only('new focused test', async ({ page }) => {\n"
                      " await expect(page.locator('#ready')).toBeVisible();\n});\n")
        self.add_file("skills/e2e-reviewer/evals/files/intentional.spec.ts",
                      "import { test } from '@playwright/test';\ntest.only('fixture', () => {});\n")
        original = HELPER.inventory(self.source)
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(HELPER_PATH), str(self.source)],
            capture_output=True, text=True, timeout=180,
            env=os.environ.copy(),
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 2, output)
        self.assertIn("original fixture scanner exit=2", output)
        self.assertIn("expected INCOMPLETE negative control verified", output)
        original_log, view_log = output.split("complete source identity verified;", 1)
        self.assertIn("#3", original_log)
        self.assertIn("#5a", original_log)
        self.assertIn('"p0Candidate": 2', original_log)
        self.assertIn('"code": "import-unpinned"', original_log)
        self.assertIn('copied-notepad.spec.cjs":35:', view_log)
        self.assertIn('copied-notepad.spec.cjs":25:', view_log)
        self.assertIn('new.spec.ts":2:', view_log)
        self.assertIn("#7", view_log)
        self.assertNotIn('intentional.spec.ts":', view_log)
        self.assertIn("discovery: INCOMPLETE", view_log)
        self.assertIn("self-scan-view: INCOMPLETE:", view_log)
        self.assertEqual(HELPER.inventory(self.source), original,
                         "product and frozen source bytes/modes must remain unchanged")


if __name__ == "__main__":
    unittest.main(verbosity=2)

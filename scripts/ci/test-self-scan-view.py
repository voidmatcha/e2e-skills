#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The CI-only frozen exception cannot hide changed or additional test source."""
from __future__ import annotations

import importlib.util
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
        self.base = Path(self.temp.name)
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

    def test_unknown_original_scan_outcomes_fail_closed(self):
        valid = ("[P0?][LLM-TRIAGE] #3 Catch fallback (1 hit)\n"
                 "[P0?][LLM-TRIAGE] #5a Conditional assertion (1 hit)\n"
                 "Summary: 2 total hit(s), 0 P0, 0 P1/P2 heuristic, 2 LLM-triage, 2 P0 candidate; 0 AST-origin hit(s)\n")
        HELPER.verify_original_candidates(subprocess.CompletedProcess([], 1, valid))
        for code, output in ((0, valid), (2, valid), (1, ""),
                             (1, valid.replace("2 P0 candidate", "1 P0 candidate")),
                             (1, valid + "INCOMPLETE: unknown\n"),
                             (1, valid.replace("#5a", "#4g"))):
            with self.subTest(code=code, output=output):
                with self.assertRaises(HELPER.ViewError):
                    HELPER.verify_original_candidates(subprocess.CompletedProcess([], code, output))

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
            env={**os.environ, "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1"},
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("original fixture scanner exit=1", output)
        original_log, view_log = output.split("complete source identity verified;", 1)
        self.assertIn("#3", original_log)
        self.assertIn("#5a", original_log)
        self.assertIn("2 P0 candidate", original_log)
        self.assertIn("copied-notepad.spec.cjs:35:", view_log)
        self.assertIn("copied-notepad.spec.cjs:25:", view_log)
        self.assertIn("new.spec.ts:2:", view_log)
        self.assertIn("#7", view_log)
        self.assertNotIn("intentional.spec.ts:", view_log)
        self.assertNotIn("INCOMPLETE", output)
        self.assertEqual(HELPER.inventory(self.source), original,
                         "product and frozen source bytes/modes must remain unchanged")


if __name__ == "__main__":
    unittest.main(verbosity=2)

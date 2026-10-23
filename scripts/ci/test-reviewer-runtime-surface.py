#!/usr/bin/env python3
"""Apache-2.0. Offline scanner runtime snapshot and digest boundary tests."""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReviewerRuntimeSurfaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "reviewer_runtime_surface_runner", ROOT / "scripts/evals/run-reviewer-holdout.py"
        )
        cls.runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.runner)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reviewer-runtime-surface-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skill = self.root / "source"
        self.skill.mkdir()
        # Real prompt material keeps the output legend and profile checks live;
        # small runtime fixtures make repeated rejection/mutation tests cheap.
        # Taxonomy lookup is snapshot material even though no prompt profile embeds it.
        prompt_paths = set().union(*self.runner.PROMPT_SKILL_PROFILES.values()) | {
            "references/grep-patterns.md"
        }
        for relative in prompt_paths:
            target = self.skill / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "skills/e2e-reviewer" / relative, target)
        self.write("scripts/scan.sh", b"#!/bin/bash\nexit 0\n")
        for relative in self.runner.SCANNER_RUNTIME_FILES:
            self.write(relative, ("runtime fixture: " + relative + "\n").encode())
        self.write("scripts/scanner/src/cli.mjs", b"export const mode = 'offline';\n")
        self.write("scripts/run-probe.mjs", b"export const mode = 'probe';\n")

    def write(self, relative, content=b"fixture\n"):
        path = self.skill / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_current_shipped_surface_stages_every_runtime_byte_and_same_digest(self):
        source = ROOT / "skills/e2e-reviewer"
        before = {path.relative_to(source).as_posix(): sha256(path)
                  for path in self.runner.skill_files(source)}
        destination = self.root / "actual-staged"
        self.runner.copy_skill_surface(source, destination)
        after = {path.relative_to(destination).as_posix(): sha256(path)
                 for path in self.runner.skill_files(destination)}
        self.assertEqual(before, after)
        self.assertTrue(self.runner.SCANNER_RUNTIME_FILES <= before.keys())
        runtime_files = {path.relative_to(source).as_posix()
                         for path in (source / "scripts/scanner").rglob("*") if path.is_file()}
        self.assertTrue(runtime_files <= before.keys())
        for relative in runtime_files:
            self.assertEqual((source / relative).read_bytes(), (destination / relative).read_bytes())
        self.assertGreater((destination / "scripts/scanner/vendor/typescript/typescript.cjs").stat().st_size, 1_000_000)
        self.assertEqual(self.runner.skill_digest(source), self.runner.skill_digest(destination))

    def test_parser_and_each_license_byte_are_digest_material(self):
        before = self.runner.skill_digest(self.skill)
        for relative in sorted(self.runner.SCANNER_RUNTIME_FILES):
            with self.subTest(path=relative):
                path = self.skill / relative
                original = path.read_bytes()
                path.write_bytes(original + b"changed\n")
                self.assertNotEqual(before, self.runner.skill_digest(self.skill))
                path.write_bytes(original)
                self.assertEqual(before, self.runner.skill_digest(self.skill))

    def test_node_probe_is_copied_and_digest_pinned(self):
        before = self.runner.skill_digest(self.skill)
        staged = self.root / "node-probe-staged"
        self.runner.copy_skill_surface(self.skill, staged)
        probe = self.skill / "scripts/run-probe.mjs"
        self.assertEqual(probe.read_bytes(), (staged / "scripts/run-probe.mjs").read_bytes())
        probe.write_bytes(probe.read_bytes() + b"// drift\n")
        self.assertNotEqual(before, self.runner.skill_digest(self.skill))

    def test_staged_parser_and_license_drift_are_rejected(self):
        workspace = self.root / "workspace"
        (workspace / ".skill").mkdir(parents=True)
        staged = workspace / ".skill/e2e-reviewer"
        self.runner.copy_skill_surface(self.skill, staged)
        expected = self.runner.skill_digest(self.skill)
        self.assertEqual(expected, self.runner.require_staged_skill_digest(workspace, expected))
        for relative in ["scripts/scanner/vendor/typescript/typescript.cjs", "scripts/scanner/LICENSE"]:
            with self.subTest(path=relative):
                path = staged / relative
                original = path.read_bytes()
                path.write_bytes(original + b"drift")
                with self.assertRaisesRegex(ValueError, "staged skill digest"):
                    self.runner.require_staged_skill_digest(workspace, expected)
                path.write_bytes(original)

    def test_exact_runtime_paths_do_not_allow_extension_or_location_expansion(self):
        for relative in [
            "scripts/LICENSE", "scripts/NOTICE", "scripts/extra.txt", "scripts/extra.cjs",
            "scripts/extra.mjs", "scripts/nested/run-probe.mjs",
            "scripts/scanner/EXTRA", "scripts/scanner/README.txt", "scripts/scanner/extra.json",
            "scripts/scanner/extra.py", "scripts/scanner/typescript.cjs",
            "scripts/scanner/src/LICENSE", "scripts/scanner/src/extra.cjs",
            "scripts/scanner/src/nested/extra.mjs", "scripts/scanner/vendor/LICENSE.txt",
            "scripts/scanner/vendor/typescript/extra.cjs", "scripts/scanner/vendor/typescript/extra.txt",
            "scripts/scanner/vendor/typescript/NOTICE",
            "scripts/scanner-copy/LICENSE", "references/LICENSE",
        ]:
            with self.subTest(path=relative):
                path = self.write(relative)
                with self.assertRaisesRegex(ValueError, "unsupported file type"):
                    self.runner.skill_files(self.skill)
                path.unlink()

    def test_license_case_is_exact_on_case_insensitive_filesystems_too(self):
        canonical = self.skill / "scripts/scanner/vendor/typescript/LICENSE.txt"
        # Remove the canonical entry before creating the wrong spelling;
        # opening license.txt beside LICENSE.txt aliases it on default macOS.
        original = canonical.read_bytes()
        canonical.unlink()
        wrong = self.write("scripts/scanner/vendor/typescript/license.txt", original)
        with self.assertRaisesRegex(ValueError, "unsupported file type"):
            self.runner.skill_files(self.skill)
        wrong.unlink()
        canonical.write_bytes(original)

    def test_canonical_parser_license_and_directory_symlinks_are_rejected(self):
        external = self.root / "external"
        external.write_bytes(b"external")
        for relative in ["scripts/scanner/vendor/typescript/typescript.cjs", "scripts/scanner/LICENSE"]:
            with self.subTest(path=relative):
                path = self.skill / relative
                original = path.read_bytes()
                path.unlink()
                path.symlink_to(external)
                with self.assertRaisesRegex(ValueError, "symlink"):
                    self.runner.skill_files(self.skill)
                path.unlink()
                path.write_bytes(original)
        link = self.skill / "scripts/scanner/src/linked"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.runner.skill_files(self.skill)

    def test_special_files_and_hidden_symlinks_are_still_rejected(self):
        fifo = self.skill / "scripts/scanner/src/pipe.mjs"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, "special file"):
            self.runner.skill_files(self.skill)
        fifo.unlink()
        hidden = self.skill / "scripts/scanner/.hidden"
        hidden.symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.runner.skill_files(self.skill)

    def test_hidden_detritus_exclusion_and_eval_metadata_guard_are_preserved(self):
        before = self.runner.skill_digest(self.skill)
        for relative in ["scripts/scanner/.DS_Store", "scripts/scanner/.cache/extra.txt",
                         "scripts/__pycache__/runtime.pyc"]:
            self.write(relative)
        self.assertEqual(before, self.runner.skill_digest(self.skill))
        self.runner.validate_skill_dir(self.skill, [])
        self.write("scripts/evals/answers.py")
        with self.assertRaisesRegex(ValueError, "eval metadata"):
            self.runner.validate_skill_dir(self.skill, [])

    def test_large_parser_stays_in_snapshot_and_out_of_every_prompt_profile(self):
        marker = b"UNIQUE_SCANNER_RUNTIME_PAYLOAD_SENTINEL"
        parser = self.write("scripts/scanner/vendor/typescript/typescript.cjs", marker * 50_000)
        workspace = self.root / "prompt-workspace"
        (workspace / ".skill").mkdir(parents=True)
        staged = workspace / ".skill/e2e-reviewer"
        self.runner.copy_skill_surface(self.skill, staged)
        (workspace / "case.spec.ts").write_text("test('example', () => {});\n")
        case = {"id": "runtime-boundary", "framework": "playwright",
                "source_files": [{"path": "case.spec.ts"}]}
        self.assertEqual(parser.read_bytes(), (staged / parser.relative_to(self.skill)).read_bytes())
        for profile in ("full", "catalog-only", "no-skill"):
            with self.subTest(profile=profile):
                selected = self.runner.prompt_skill_files(staged, profile)
                self.assertFalse(any("scanner" in path.relative_to(staged).parts for path in selected))
                before = self.runner.render_prompt(case, workspace, prompt_profile=profile)
                digest = self.runner.prompt_skill_digest(staged, profile)
                self.assertNotIn(marker.decode(), before)
                self.assertNotIn("BEGIN_REVIEWER_SKILL scripts/", before)
                path = staged / "scripts/scanner/vendor/typescript/typescript.cjs"
                path.write_bytes(path.read_bytes() + b"changed\n")
                self.assertEqual(before, self.runner.render_prompt(case, workspace, prompt_profile=profile))
                self.assertEqual(digest, self.runner.prompt_skill_digest(staged, profile))
        for profile in self.runner.PROMPT_SKILL_PROFILES:
            self.assertFalse(any(path.suffix == ".cjs" for path in self.runner.prompt_skill_files(staged, profile)))


if __name__ == "__main__":
    unittest.main()

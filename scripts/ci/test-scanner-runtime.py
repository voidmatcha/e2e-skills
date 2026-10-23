#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline generation contract tests; all mutations stay in disposable fixtures."""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPOSITORY = Path(__file__).resolve().parents[2]
BUILDER = REPOSITORY / "scripts/dev/build-scanner-runtime.py"
GENERATED = REPOSITORY / "skills/e2e-reviewer/scripts/scanner"
spec = importlib.util.spec_from_file_location("scanner_runtime_builder", BUILDER)
builder = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(builder)


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="scanner-runtime-test-")
        cls.root = Path(cls.temporary.name).resolve()
        cls.source = cls.root / "package"
        cls.output = cls.root / "runtime"
        cls.dependency = cls.root / "typescript"
        (cls.source / "src").mkdir(parents=True)
        (cls.source / "src/cli.mjs").write_text("import {version} from './source.mjs';\nif(false) await import('./optional.mjs');\nconsole.log(version);\n")
        (cls.source / "src/source.mjs").write_text("import ts from 'typescript';\nexport const version=ts.version;\n")
        (cls.source / "src/optional.mjs").write_text("import fs from 'node:fs';\nexport const value=1;\n")
        (cls.source / "src/check-cli.mjs").write_text("throw new Error('unreachable');\n")
        for name in ("LICENSE", "NOTICE"):
            shutil.copy2(REPOSITORY / "packages/scanner" / name, cls.source / name)
        for original, relative in builder.VENDOR_PATHS.items():
            destination = cls.dependency / original
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(GENERATED / relative, destination)
        (cls.dependency / "package.json").write_text(json.dumps({"name": "typescript", "version": builder.VERSION}))
        cls.invoke("--write", "--typescript-dir", str(cls.dependency))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def invoke(cls, *arguments, success=True):
        run = subprocess.run([sys.executable, str(BUILDER), "--source-root", str(cls.source),
                              "--output", str(cls.output), *arguments], text=True, capture_output=True, timeout=45)
        if (run.returncode == 0) != success:
            raise AssertionError((run.returncode, run.stdout, run.stderr))
        return run

    @contextlib.contextmanager
    def replaced(self, file, data):
        before = file.read_bytes()
        try:
            file.write_bytes(data)
            yield
        finally:
            file.write_bytes(before)

    def test_actual_generated_runtime_is_current(self):
        result = subprocess.run([sys.executable, str(BUILDER), "--check"], capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_deterministic_rebuild_and_exact_closure(self):
        before = {str(file.relative_to(self.output)): (hashlib.sha256(file.read_bytes()).hexdigest(), file.stat().st_mtime_ns)
                  for file in self.output.rglob("*") if file.is_file()}
        self.invoke("--write", "--typescript-dir", str(self.dependency))
        after = {str(file.relative_to(self.output)): (hashlib.sha256(file.read_bytes()).hexdigest(), file.stat().st_mtime_ns)
                 for file in self.output.rglob("*") if file.is_file()}
        self.assertEqual(before, after)
        self.assertTrue((self.output / "src/optional.mjs").is_file())
        self.assertFalse((self.output / "src/check-cli.mjs").exists())
        self.assertIn(builder.NEW_IMPORT, (self.output / "src/source.mjs").read_bytes())
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertNotIn("manifest.json", manifest["files"])
        for name, record in manifest["files"].items():
            data = (self.output / name).read_bytes()
            self.assertEqual(record, {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    def test_check_needs_no_external_dependency(self):
        hidden = self.root / "typescript-hidden"
        self.dependency.rename(hidden)
        try:
            self.invoke("--check")
        finally:
            hidden.rename(self.dependency)

    def test_write_requires_explicit_external_dependency(self):
        self.invoke("--write", success=False)
        result = self.invoke("--write", "--typescript-dir", str(self.source / "node_modules/typescript"), success=False)
        self.assertIn("outside the source checkout", result.stderr)
        self.invoke("--check", "--typescript-dir", str(self.dependency), success=False)

    def test_source_drift_and_new_dependency_are_detected(self):
        optional = self.source / "src/optional.mjs"
        with self.replaced(optional, b"export const value=2;\n"):
            self.assertIn("runtime drift", self.invoke("--check", success=False).stderr)
        added = self.source / "src/added.mjs"
        added.write_text("export const added=1;\n")
        try:
            with self.replaced(optional, b"export {added} from './added.mjs';\n"):
                self.invoke("--check", success=False)
                self.invoke("--write", "--typescript-dir", str(self.dependency))
                self.assertTrue((self.output / "src/added.mjs").exists())
                self.invoke("--check")
        finally:
            added.unlink()
            (self.output / "src/added.mjs").unlink(missing_ok=True)
            self.invoke("--write", "--typescript-dir", str(self.dependency))

    def test_missing_or_invalid_source_and_dynamic_import_fail(self):
        file = self.source / "src/optional.mjs"
        saved = file.read_bytes()
        file.unlink()
        try:
            self.assertIn("missing source module", self.invoke("--check", success=False).stderr)
        finally:
            file.write_bytes(saved)
        for data in (b"export const = (", b"await import(variable);", b"import bad from 'unapproved-package';"):
            with self.replaced(file, data):
                self.invoke("--check", success=False)

    def test_missing_or_changed_generated_module_and_manifest_fail(self):
        for relative in ("src/optional.mjs", "manifest.json"):
            file = self.output / relative
            before = file.read_bytes()
            file.unlink()
            try:
                self.invoke("--check", success=False)
            finally:
                file.write_bytes(before)
            with self.replaced(file, b"corrupt"):
                self.invoke("--check", success=False)

    def test_vendor_runtime_and_licenses_have_fixed_hashes(self):
        for relative in builder.VENDOR_PATHS.values():
            file = self.output / relative
            with self.replaced(file, b"throw new Error('untrusted parser must not run');"):
                result = self.invoke("--check", success=False)
                self.assertIn("TypeScript original hash mismatch", result.stderr)
                self.assertNotIn("source dependency closure failed", result.stderr)
        with self.replaced(self.dependency / "lib/typescript.js", b"bad"):
            self.invoke("--write", "--typescript-dir", str(self.dependency), success=False)
        with self.replaced(self.dependency / "package.json", b'{"name":"typescript","version":"0.0.0"}'):
            self.invoke("--write", "--typescript-dir", str(self.dependency), success=False)

    def test_unexpected_file_is_rejected_and_never_deleted(self):
        extra = self.output / "keep-me.txt"
        extra.write_text("unrelated")
        try:
            for args in [("--check",), ("--write", "--typescript-dir", str(self.dependency))]:
                self.assertIn("unexpected runtime files", self.invoke(*args, success=False).stderr)
                self.assertEqual(extra.read_text(), "unrelated")
        finally:
            extra.unlink()

    def test_symlink_source_output_and_vendor_fail_closed(self):
        file = self.output / "src/optional.mjs"
        saved = file.read_bytes()
        file.unlink()
        file.symlink_to(self.source / "src/optional.mjs")
        try:
            self.invoke("--check", success=False)
            self.invoke("--write", "--typescript-dir", str(self.dependency), success=False)
        finally:
            file.unlink()
            file.write_bytes(saved)
        link = self.root / "linked-runtime"
        link.symlink_to(self.output, target_is_directory=True)
        try:
            self.invoke("--check", "--output", str(link), success=False)
        finally:
            link.unlink()
        for file in (self.source / "src/optional.mjs", self.dependency / "LICENSE.txt"):
            saved = file.read_bytes()
            target = self.root / "symlink-target"
            target.write_bytes(saved)
            file.unlink()
            file.symlink_to(target)
            try:
                self.invoke("--write", "--typescript-dir", str(self.dependency), success=False)
            finally:
                file.unlink()
                file.write_bytes(saved)
                target.unlink()

    def test_fixed_node_resolution_ignores_path_and_node_startup_injection(self):
        directory = self.root / "path-bin"
        directory.mkdir()
        marker = self.root / "path-node-executed"
        fake = directory / "node"
        fake.write_text("#!/bin/sh\ntouch '" + str(marker) + "'\nexit 99\n")
        fake.chmod(0o755)
        environment = dict(os.environ, PATH=str(directory) + ":/usr/bin:/bin",
                           NODE_OPTIONS="--require=/nonexistent-scanner-runtime-startup.cjs")
        run = subprocess.run([sys.executable, str(BUILDER), "--check"], env=environment,
                             capture_output=True, text=True, timeout=45)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(marker.exists())
        environment["PATH"] = "/usr/bin:/bin"
        run = subprocess.run([sys.executable, str(BUILDER), "--check"], env=environment,
                             capture_output=True, text=True, timeout=45)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_node_resolution_rejects_project_writable_and_old_executables(self):
        project = self.source / "node"
        writable = self.root / "writable-node"
        old = self.root / "old-node"
        good = self.root / "good-node"
        for file in (project, writable, old, good):
            file.write_text("fixture, never executed")
            file.chmod(0o755)
        writable.chmod(0o775)
        with mock.patch.object(builder, "NODE_PATHS", tuple(map(str, (project, writable, old, good)))), \
             mock.patch.object(builder.subprocess, "run", side_effect=[
                 subprocess.CompletedProcess([], 2), subprocess.CompletedProcess([], 0)]) as run:
            self.assertEqual(builder.trusted_node(self.source, {}), str(good))
            self.assertEqual([call.args[0][0] for call in run.call_args_list], [str(old), str(good)])
        with mock.patch.object(builder, "NODE_PATHS", (str(project), str(writable))), \
             mock.patch.object(builder.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "trusted standard"):
                builder.trusted_node(self.source, {})
            run.assert_not_called()

    def test_node_startup_injection_is_not_executed(self):
        before = os.environ.get("NODE_OPTIONS")
        os.environ["NODE_OPTIONS"] = "--require=/nonexistent-scanner-runtime-startup.cjs"
        try:
            self.invoke("--check")
        finally:
            if before is None:
                os.environ.pop("NODE_OPTIONS", None)
            else:
                os.environ["NODE_OPTIONS"] = before


if __name__ == "__main__":
    unittest.main()

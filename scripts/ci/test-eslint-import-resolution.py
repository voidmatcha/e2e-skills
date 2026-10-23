#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Preserve the frozen shell backend's package-resolution mechanism tests.

Current Node product trust and ESLint loading are checked separately by
test-local-eslint-node.py and the scanner package tests. These tests do not
establish current-product behavior.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from legacy_scanner_oracle import legacy_scanner_file


ROOT = Path(__file__).resolve().parents[2]
NODE_CANDIDATES = (
    "/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node", "/bin/node",
)


def trusted_node_executable(override=None, repository=ROOT) -> Path:
    """Match ci-local.sh: an invalid explicit override never falls back."""
    repository = repository.resolve()
    raw_override = os.fspath(override) if override is not None else os.environ.get("E2E_SKILLS_NODE_BIN", "")
    for raw in (raw_override,) if raw_override else NODE_CANDIDATES:
        if not raw.startswith("/"):
            continue
        try:
            candidate = Path(raw).resolve(strict=True)
            if not candidate.is_file() or not os.access(candidate, os.X_OK):
                continue
            if candidate.stat().st_mode & 0o022:
                continue
            if candidate == repository or repository in candidate.parents:
                continue
        except OSError:
            continue
        return candidate
    raise ValueError("trusted Node executable unavailable or explicit override rejected")


class ImportResolutionTests(unittest.TestCase):
    scanner = legacy_scanner_file()
    node_override = None

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="e2e-import-resolver-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.project = self.base / "project"
        self.modules = self.project / "node_modules"
        self.modules.mkdir(parents=True)
        (self.modules / ".bin").mkdir()
        bodies = re.findall(
            r"<<'EOFRES'\n(.*?)\nEOFRES(?:\n|$)", self.scanner.read_text(), re.S
        )
        self.assertEqual(len(bodies), 1, "Expected exactly one frozen legacy resolver heredoc")
        self.resolver = self.base / "resolve.cjs"
        self.resolver.write_text(bodies[0] + "\n")
        self.node = trusted_node_executable(self.node_override)
        # No ambient runtime injection or credential variables enter Node.
        self.env = {
            "PATH": f"{self.modules / '.bin'}:/usr/bin:/bin",
            "HOME": str(self.base),
            "LANG": "C",
            "LC_ALL": "C",
        }
        self.marker = self.base / "module-body-executed"
        self.import_only = self.modules / "scanner-import-only-fixture"
        self.import_only.mkdir()
        (self.import_only / "package.json").write_text(json.dumps({
            "name": self.import_only.name,
            "type": "module",
            "exports": {".": {"import": "./entry.mjs"}},
        }))
        (self.import_only / "entry.mjs").write_text(
            "import fs from 'node:fs';\n"
            f"fs.writeFileSync({json.dumps(str(self.marker))}, 'executed');\n"
            "export default {};\n"
        )
        self.commonjs = self.modules / "scanner-commonjs-fixture"
        self.commonjs.mkdir()
        (self.commonjs / "package.json").write_text(json.dumps({
            "name": self.commonjs.name, "main": "entry.cjs",
        }))
        (self.commonjs / "entry.cjs").write_text(
            f"require('node:fs').writeFileSync({json.dumps(str(self.marker))}, 'executed');\n"
            "module.exports = {};\n"
        )

    def resolve_packages(self, *names, cwd=None):
        return subprocess.run(
            [str(self.node), str(self.resolver), *names],
            cwd=cwd or self.project, env=self.env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, check=False,
        )

    def test_import_only_and_commonjs_without_evaluation(self):
        result = self.resolve_packages(self.import_only.name, self.commonjs.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [
            str(self.import_only / "entry.mjs"), str(self.commonjs / "entry.cjs"),
        ])
        self.assertFalse(self.marker.exists(), "Resolution evaluated a module body")

    def test_first_candidate_resolves_outside_project_cwd(self):
        outside = self.base / "outside"
        outside.mkdir()
        result = self.resolve_packages(self.import_only.name, self.commonjs.name, cwd=outside)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [
            str(self.import_only / "entry.mjs"), str(self.commonjs / "entry.cjs"),
        ])
        self.assertFalse(self.marker.exists())

    def test_project_node_modules_fallback(self):
        self.env["PATH"] = "/usr/bin:/bin"
        result = self.resolve_packages(self.import_only.name, self.commonjs.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [
            str(self.import_only / "entry.mjs"), str(self.commonjs / "entry.cjs"),
        ])
        self.assertFalse(self.marker.exists())

    def test_missing_package_fails_closed(self):
        result = self.resolve_packages("scanner-nonexistent-fixture-package")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("unresolvable: scanner-nonexistent-fixture-package", result.stderr)
        self.assertFalse(self.marker.exists())


class NodeOverrideTests(unittest.TestCase):
    def test_nvm_override_without_standard_node(self):
        real_node = trusted_node_executable(ImportResolutionTests.node_override)
        with tempfile.TemporaryDirectory(prefix="e2e-node-override-") as temporary:
            nvm_node = Path(temporary) / ".nvm/versions/node/v-test/bin/node"
            nvm_node.parent.mkdir(parents=True)
            nvm_node.symlink_to(real_node)
            with mock.patch(__name__ + ".NODE_CANDIDATES", ("/nonexistent/standard/node",)), mock.patch.dict(
                os.environ, {"E2E_SKILLS_NODE_BIN": str(nvm_node)}
            ):
                self.assertEqual(trusted_node_executable(), real_node)

    def test_invalid_override_does_not_fall_back(self):
        real_node = trusted_node_executable(ImportResolutionTests.node_override)
        with mock.patch(__name__ + ".NODE_CANDIDATES", (str(real_node),)):
            for raw in ("relative/node", "/nonexistent/override/node"):
                with self.subTest(override=raw), self.assertRaises(ValueError):
                    trusted_node_executable(raw)

    def test_writable_or_repository_runtime_rejected(self):
        with tempfile.TemporaryDirectory(prefix="e2e-rejected-node-") as temporary:
            base = Path(temporary).resolve()
            executable = base / "node"
            executable.write_text("#!/bin/sh\nexit 99\n")
            executable.chmod(0o777)
            with self.assertRaises(ValueError):
                trusted_node_executable(executable)
            executable.chmod(0o755)
            with self.assertRaises(ValueError):
                trusted_node_executable(executable, repository=base)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", type=Path, default=ImportResolutionTests.scanner)
    parser.add_argument("--node", type=Path, help="Trusted runtime, overriding E2E_SKILLS_NODE_BIN")
    args, unittest_args = parser.parse_known_args()
    ImportResolutionTests.scanner = args.scanner.resolve()
    try:
        ImportResolutionTests.node_override = trusted_node_executable(args.node)
    except ValueError as error:
        parser.error(str(error))
    unittest.main(argv=[__file__, *unittest_args])

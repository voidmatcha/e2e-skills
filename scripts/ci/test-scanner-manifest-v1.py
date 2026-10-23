#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Current Node inventory preserves the original unreadable-file regressions.

Historical shell inventory spawned many Python processes per candidate; these
unchanged fixtures protect the failure boundary rather than that implementation.
Every unreadable regular file must yield a named fingerprint diagnostic and an
INCOMPLETE/exit-2 report. A complete focused-test scan still exits 1.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCAN = ROOT / "skills/e2e-reviewer/scripts/scan.sh"

SPEC = (
    "import { test, expect } from '@playwright/test';\n"
    "test('a', async ({ page }) => {\n"
    "  await expect(page.getByTestId('x')).toBeVisible();\n});\n"
)


def run(tree: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", "-p", str(SCAN), str(tree), "--format", "json"],
        capture_output=True,
        text=True,
        timeout=300,
        env={key: value for key, value in os.environ.items() if not key.startswith("E2E_SMELL_")},
    )


class ManifestTests(unittest.TestCase):
    def test_an_unfingerprintable_candidate_stops_the_scan(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tree = Path(raw)
            (tree / "tests").mkdir()
            (tree / "tests/ok.spec.ts").write_text(SPEC, encoding="utf-8")
            locked = tree / "tests/locked.spec.ts"
            locked.write_text(SPEC, encoding="utf-8")
            locked.chmod(0o000)
            try:
                result = run(tree)
            finally:
                locked.chmod(0o644)

        out = result.stdout + result.stderr
        self.assertEqual(
            result.returncode, 2,
            "a candidate that cannot be fingerprinted must fail the scan closed",
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["schema"], "e2e-skills-node-scan-v1")
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertIs(report["execution"]["complete"], False)
        self.assertEqual(report["execution"]["exitCode"], 2)
        self.assertTrue(any(item["code"] == "fingerprint-unavailable" and
                            item["file"].endswith("/locked.spec.ts")
                            for item in report["execution"]["diagnostics"]), out)
        self.assertEqual(report["findings"], [], "unfingerprinted source cannot produce a clean verdict")

    def test_a_clean_tree_still_scans(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tree = Path(raw)
            (tree / "tests").mkdir()
            (tree / "tests/focused.spec.ts").write_text(
                "import { test, expect } from '@playwright/test';\n"
                "test.only('a', async ({ page }) => {\n"
                "  await expect(page.getByTestId('x')).toBeVisible();\n});\n",
                encoding="utf-8",
            )
            result = run(tree)

        out = result.stdout + result.stderr
        report = json.loads(result.stdout)
        self.assertEqual(report["schema"], "e2e-skills-node-scan-v1")
        self.assertEqual(report["status"], "COMPLETE")
        self.assertIs(report["execution"]["complete"], True)
        self.assertEqual(report["execution"]["diagnostics"], [])
        self.assertEqual([(hit["patternId"], hit["line"]) for hit in report["findings"]], [("#7", 2)])
        self.assertEqual(result.returncode, 1, "the focused-test finding still exits 1")

    def test_every_candidate_is_fingerprinted_not_just_the_first(self) -> None:
        """One interpreter per pass must not mean one file per pass."""
        with tempfile.TemporaryDirectory() as raw:
            tree = Path(raw)
            (tree / "tests").mkdir()
            for index in range(6):
                (tree / f"tests/s{index}.spec.ts").write_text(SPEC, encoding="utf-8")
            # The failure is last in path order, so reaching it proves the pass
            # did not stop after the first record.
            locked = tree / "tests/zz_last.spec.ts"
            locked.write_text(SPEC, encoding="utf-8")
            locked.chmod(0o000)
            try:
                result = run(tree)
            finally:
                locked.chmod(0o644)

        out = result.stdout + result.stderr
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertIs(report["execution"]["complete"], False)
        self.assertTrue(any(item["code"] == "fingerprint-unavailable" and
                            item["file"].endswith("/zz_last.spec.ts")
                            for item in report["execution"]["diagnostics"]), out)



if __name__ == "__main__":
    unittest.main(verbosity=2)

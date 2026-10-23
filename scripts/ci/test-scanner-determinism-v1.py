#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Two scans of the same tree must produce the same bytes.

Found while verifying a performance change: three runs of the unmodified
scanner over one 785-file repository produced two different outputs. The hits
were the same -- same count, same headers, same sorted set -- but whole
file-blocks appeared in different positions from run to run.

The cause is ripgrep's parallel search: with no `--sort`, each file's block is
printed when its worker finishes, so the order of files is a race. Measured on
one rule's pattern over that tree, the default flags gave 9 distinct file
orderings in 20 runs.

Two things made this worth fixing rather than tolerating. A user who diffs two
scans of the same repository sees findings that appear to move or vanish. And
it quietly invalidates byte comparison as a verification method -- during this
work a byte diff reported that a change had altered the findings when it had
not.

The tree below needs several matching files for the race to be observable; a
single-file fixture cannot reorder and would pass even against the defect.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCAN = ROOT / "skills/e2e-reviewer/scripts/scan.sh"

# Enough files, each carrying the same smell, that ripgrep searches them in
# parallel and can finish them out of order.
FILE_COUNT = 8
RUNS = 3


def build_tree(tmp: Path) -> None:
    for index in range(FILE_COUNT):
        spec = tmp / f"tests/spec_{index:02d}.spec.ts"
        spec.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(
            f"test('case {n}', async ({{ page }}) => {{\n"
            f"  await page.waitForTimeout({100 + n});\n}});"
            for n in range(12)
        )
        spec.write_text(
            "import { test, expect } from '@playwright/test';\n\n" + body + "\n",
            encoding="utf-8",
        )


def scan(tree: Path) -> tuple[str, dict]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("E2E_SMELL_")}
    result = subprocess.run(
        ["/bin/bash", "-p", str(SCAN), str(tree), "--format", "json", "--fail-on", "none"],
        capture_output=True, text=True, timeout=300, env=env,
    )
    if result.returncode != 0 or result.stderr:
        raise AssertionError(f"scan did not complete: {result.returncode}\n{result.stdout}\n{result.stderr}")
    report = json.loads(result.stdout)
    if (report.get("schema") != "e2e-skills-node-scan-v1" or report.get("status") != "COMPLETE"
            or report.get("execution", {}).get("complete") is not True
            or report["execution"].get("diagnostics") != [] or not report.get("findings")):
        raise AssertionError(f"an error/empty report cannot prove finding determinism: {report}")
    return result.stdout, report


class DeterminismTests(unittest.TestCase):
    def test_identical_failures_cannot_pass_as_deterministic_scans(self) -> None:
        failure = subprocess.CompletedProcess([], 2, "", "INCOMPLETE: unavailable runtime")
        with patch("subprocess.run", return_value=failure):
            for _ in range(RUNS):
                with self.assertRaisesRegex(AssertionError, "scan did not complete"):
                    scan(Path("unused"))


    def test_repeated_scans_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tree = Path(raw)
            build_tree(tree)
            outputs = [scan(tree)[0] for _ in range(RUNS)]

        # Fail with something a reader can act on: which lines moved.
        first = outputs[0].splitlines()
        for index, other in enumerate(outputs[1:], start=2):
            lines = other.splitlines()
            self.assertEqual(
                sorted(first), sorted(lines),
                "runs disagree on the set of output lines, not merely their order",
            )
            self.assertEqual(
                first, lines,
                f"run 1 and run {index} report the same lines in a different "
                "order; a scan must be reproducible byte for byte",
            )

    def test_hits_are_reported_in_path_order(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tree = Path(raw)
            build_tree(tree)
            _, report = scan(tree)

        hits = [hit for hit in report["findings"] if hit["patternId"] == "#9"]
        self.assertEqual(len(hits), FILE_COUNT * 12)
        self.assertTrue(all(hit["origin"] == "ast" for hit in hits))
        files = []
        for hit in hits:
            if not files or files[-1] != hit["file"]:
                files.append(hit["file"])
        self.assertGreater(len(files), 1, "the fixture must produce multi-file output")
        # Each file's block appears once, and blocks ascend by path.
        self.assertEqual(
            len(files), len(set(files)),
            "a file's hits must be reported as one contiguous block",
        )
        self.assertEqual(files, sorted(files), "file blocks must ascend by path")


AST_FILE_COUNT = 8


def build_ast_tree(tmp: Path) -> None:
    """Original count-assertion fixture, now checked through the canonical AST report.

    The old ast-grep stream could reorder these hits. The current parser must
    retain all 16 count-read candidates in repeatable canonical order without
    an optional-tool skip or accepting identical error outputs.
    """
    for index in range(AST_FILE_COUNT):
        spec = tmp / f"tests/ast_{index:02d}.spec.ts"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(
            "import { test, expect } from '@playwright/test';\n\n"
            f"test('case {index}', async ({{ page }}) => {{\n"
            "  expect(await page.locator('.x').count()).toBe(3);\n"
            "  expect(await page.locator('.y').count()).toBe(4);\n});\n",
            encoding="utf-8",
        )


class ASTDeterminismTests(unittest.TestCase):
    def test_ast_hits_are_reported_in_a_stable_order(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tree = Path(raw)
            build_ast_tree(tree)
            outputs = [scan(tree)[0] for _ in range(RUNS)]

        first_report = json.loads(outputs[0])
        count_hits = [hit for hit in first_report["findings"] if hit["patternId"] == "#4c-4e"]
        self.assertEqual(len(count_hits), AST_FILE_COUNT * 2)
        self.assertTrue(all(hit["origin"] == "ast" for hit in count_hits))

        for index, other in enumerate(outputs[1:], start=2):
            self.assertEqual(
                sorted(outputs[0].splitlines()), sorted(other.splitlines()),
                "AST runs disagree on the set of output lines",
            )
            self.assertEqual(
                outputs[0].splitlines(), other.splitlines(),
                f"AST run 1 and run {index} report the same hits in a "
                "different order",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

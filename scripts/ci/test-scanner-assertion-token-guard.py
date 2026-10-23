#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The assertion-token rewrite must refuse an unanchored discovery pattern.

`run_check` rewrites a rule's discovery pattern into
`^(?=lookahead)${pattern#^}` so the multiline assertion-token lookahead can
cross lines while the original expression keeps matching where it used to.
`${pattern#^}` only strips a *leading* `^`; if the original pattern was never
anchored, the rewrite still prepends `^`, which silently narrows the match to
column zero instead of the caller's intended position anywhere in the line.
Every shipped assertion-token call site anchors its pattern today, so this
never fires in production, but nothing enforced that invariant -- a future
caller passing an unanchored pattern would get silent under-matching instead
of an error. `require_anchored_discovery_pattern` (extracted from scan.sh
verbatim, exercised standalone) is the fail-fast guard for that case.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.legacy_scanner_oracle import legacy_scanner_file

ROOT = Path(__file__).resolve().parents[2]
# Legacy shell mechanism verification only; not a current Node product gate.
SCAN = legacy_scanner_file()


def extract_function(source: str, name: str) -> str:
    start = source.index(name + "() {")
    end = source.index("\n}\n", start) + 3
    return source[start:end]


FUNCTION = extract_function(SCAN.read_text(), "require_anchored_discovery_pattern")


def run_guard(check_id: str, pattern: str):
    command = FUNCTION + "\nrequire_anchored_discovery_pattern \"$1\" \"$2\"\n"
    return subprocess.run(
        ["/bin/bash", "-p", "-c", command, "guard-test", check_id, pattern],
        capture_output=True,
        text=True,
        timeout=5,
    )


class AssertionTokenGuardTests(unittest.TestCase):
    def test_anchored_pattern_passes_through(self):
        result = run_guard("#4f", "^[[:space:]]*expect[[:space:]]*\\(")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_unanchored_pattern_fails_closed(self):
        result = run_guard("#4f", "expect[[:space:]]*\\(")
        self.assertEqual(result.returncode, 2)
        self.assertIn("#4f", result.stderr)
        self.assertIn("anchored", result.stderr)

    def test_pattern_anchored_only_mid_expression_still_fails_closed(self):
        # A caret appearing after the start of the pattern (e.g. inside a
        # character class or group) must not satisfy the anchor requirement --
        # only a genuine leading ^ does.
        result = run_guard("#15", "(?:^|;)[[:space:]]*expect\\(")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()

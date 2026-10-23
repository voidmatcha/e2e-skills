#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""A scope predicate's error status must never be cached as "not in scope".

`rule_scope_predicate` memoizes a file predicate's in/out verdict in
`$SCOPE_STATE_DIR/<predicate>.{in,out}` so repeated checks on the same file
across many rules cost one evaluation. The predicate convention elsewhere in
scan.sh is exit 0 = true, 1 = false, >=2 = error (see e.g. `abort_on_rg_error`
and the Tier 3 discovery guards). Before this fix, any non-zero exit --
including a real failure such as a crashed `rg`/`python3` helper or an
`E2E_SMELL_PYTHON_BIN` override with an unrelated bug -- was written straight
into the `.out` cache as a permanent, silently wrong "not in scope"
determination for that file. A transient error would then be indistinguishable
from a legitimate negative for the rest of the scan. Status >=2 must instead
propagate to the caller without touching the cache, so the same file gets
re-evaluated (and can still error loudly) on the next call instead of being
locked into a false negative.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
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


SOURCE = SCAN.read_text()
FUNCTION = extract_function(SOURCE, "rule_scope_predicate")
ABORTING_FUNCTION = extract_function(SOURCE, "rule_scope_predicate_or_abort")
CALLER_FUNCTION = extract_function(SOURCE, "file_in_rule_scope")


def run_predicate(state_dir: str, predicate_body: str, file_arg: str = "target.spec.ts"):
    command = (
        FUNCTION
        + "\nSCOPE_STATE_DIR=\"$1\"\n"
        + "fake_predicate() {\n"
        + predicate_body
        + "\n}\n"
        + "rule_scope_predicate fake_predicate \"$2\"\n"
    )
    return subprocess.run(
        ["/bin/bash", "-p", "-c", command, "predicate-test", state_dir, file_arg],
        capture_output=True,
        text=True,
        timeout=5,
    )


class RuleScopePredicateCacheTests(unittest.TestCase):
    def test_true_result_is_cached_as_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_predicate(tmp, "return 0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((Path(tmp) / "fake_predicate.in").read_text().strip(), "target.spec.ts")
            self.assertFalse((Path(tmp) / "fake_predicate.out").exists())

    def test_false_result_is_cached_as_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_predicate(tmp, "return 1")
            self.assertEqual(result.returncode, 1)
            self.assertEqual((Path(tmp) / "fake_predicate.out").read_text().strip(), "target.spec.ts")

    def test_error_status_propagates_without_caching_a_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_predicate(tmp, "return 2")
            self.assertEqual(result.returncode, 2)
            self.assertFalse((Path(tmp) / "fake_predicate.out").exists())
            self.assertFalse((Path(tmp) / "fake_predicate.in").exists())

    def test_error_status_is_retried_not_locked_in(self):
        # A predicate that errors once then succeeds must still be consulted
        # the second time -- a cached false-negative would skip it silently.
        with tempfile.TemporaryDirectory() as tmp:
            counter = Path(tmp) / "calls"
            body = (
                f'c=$(cat "{counter}" 2>/dev/null || echo 0); c=$((c + 1)); '
                f'printf "%s" "$c" > "{counter}"; '
                '[[ "$c" -eq 1 ]] && return 2; return 0'
            )
            first = run_predicate(tmp, body)
            self.assertEqual(first.returncode, 2)
            second = run_predicate(tmp, body)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((Path(tmp) / "fake_predicate.in").read_text().strip(), "target.spec.ts")

    def test_cached_out_short_circuits_without_reinvoking_predicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "fake_predicate.out").write_text("target.spec.ts\n")
            result = run_predicate(tmp, 'echo "should not run" >&2; return 0')
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, "")

    def test_file_scope_caller_fails_closed_on_predicate_error(self):
        # Exercise the real boolean caller: without the aborting wrapper, the
        # `&& exception=1` expression consumes exit 2 as ordinary false and an
        # already-IN file is incorrectly admitted.
        with tempfile.TemporaryDirectory() as tmp:
            command = (
                FUNCTION
                + "\n"
                + ABORTING_FUNCTION
                + "\n"
                + CALLER_FUNCTION
                + "\nSCOPE_STATE_DIR=\"$1\"\n"
                + "SCANNER_TEMP_ROOT=\"$1\"\n"
                + "scope_status() { printf 'IN\\n'; }\n"
                + "source_has_unresolved_test_import() { return 2; }\n"
                + "file_has_resolved_framework_reference() { return 1; }\n"
                + "file_in_playwright_scope() { return 1; }\n"
                + "file_in_cypress_scope() { return 1; }\n"
                + "file_in_rule_scope target.spec.ts P0 '#7' ',e2e,'\n"
            )
            result = subprocess.run(
                ["/bin/bash", "-p", "-c", command, "caller-test", tmp],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("scope predicate source_has_unresolved_test_import failed", result.stderr)
            self.assertIn(
                "source_has_unresolved_test_import\ttarget.spec.ts\t2",
                (Path(tmp) / "scope-errors").read_text(),
            )


if __name__ == "__main__":
    unittest.main()

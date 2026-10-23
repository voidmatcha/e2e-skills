#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Frozen legacy shell catch/finally mechanism verification, not Node coverage."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import sys
import unittest



sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.legacy_scanner_oracle import legacy_scanner_file

ROOT = Path(__file__).resolve().parents[2]
SCANNER = legacy_scanner_file()
ENV = {
    **os.environ,
    "LC_ALL": "C",
    "LC_CTYPE": "C",
    "LANG": "C",
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
}


def resolve_rg() -> str:
    configured = os.environ.get("E2E_SMELL_RG_BIN")
    candidates = [configured] if configured else [
        "/opt/homebrew/bin/rg",
        "/usr/local/bin/rg",
        "/usr/bin/rg",
        "/bin/rg",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.is_absolute() and path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise RuntimeError("Set E2E_SMELL_RG_BIN to an absolute executable ripgrep path")


def scanner_function(source: str, name: str) -> str:
    match = re.search(
        r"^" + re.escape(name) + r"\(\) \{\n.*?^\}\n",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"Scanner function missing: {name}")
    return match.group()


class CatchDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCANNER.read_text(encoding="utf-8")
        cls.rg = resolve_rg()
        start = cls.source.index("\nrun_check() {\n") + 1
        stop = cls.source.index("  local raw_output\n", start)
        cls.discovery_function = (
            cls.source[start:stop].replace("run_check() {", "discovery() {", 1)
            + '  printf "%s\\0" "$pattern" "${context_options[@]}"\n}\n'
        )

    def fixture(self, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "case.js"
        path.write_text(source, encoding="utf-8")
        return path

    def shell(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", "-p", "-c", script],
            capture_output=True,
            text=True,
            env=ENV,
            timeout=10,
        )

    def discovery_options(self, mode: str) -> tuple[str, list[str]]:
        flag = 'swallowed-finally-return' if mode == 'finally-return' else f'catch-{mode}'
        calls = [
            line for line in self.source.splitlines()
            if line.startswith("run_check ") and f"{flag}'" in line
        ]
        self.assertEqual(len(calls), 1, f"Expected one catch-{mode} rule")
        script = (
            "ALL_CODE_GLOB='*.js'\n"
            + self.discovery_function
            + calls[0].replace("run_check ", "discovery ", 1)
            + "\n"
        )
        result = self.shell(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        pattern, *options = result.stdout.split("\0")
        return pattern, [option for option in options if option]

    def discover(self, path: Path, mode: str, *, unfiltered: bool = False) -> list[str]:
        if unfiltered:
            self.assertEqual(mode, 'finally-return')
            call = next(line for line in self.source.splitlines()
                        if line.startswith('run_check ') and "swallowed-finally-return'" in line)
            pattern, options = shlex.split(call)[4], []
        else:
            pattern, options = self.discovery_options(mode)
        result = subprocess.run(
            [self.rg, "-nP", "-H", "--color", "never", *options, pattern, "--", str(path)],
            capture_output=True,
            text=True,
            env=ENV,
            timeout=10,
        )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.stdout.splitlines()

    def accepted(self, hit: str, mode: str) -> bool:
        predicate = ('swallowed_assertion_hit_matches' if mode == 'finally-return'
                     else 'catch_callback_hit_matches')
        script = (
            "scanner_rg() { " + shlex.quote(self.rg) + ' "$@"; }\n'
            + scanner_function(self.source, "locator_assertion_source")
            + scanner_function(self.source, predicate)
            # Isolate discovery from graph traversal: both paths receive the
            # same accepting binding oracle. The lexical classifier is real.
            + "PLAYWRIGHT_ASYNC_MATCHERS='toBeVisible'\n"
            + "playwright_expect_binding() { return 0; }\n"
            + shlex.join([predicate, hit, mode])
            + "\n"
        )
        result = self.shell(script)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode == 0

    def bounded(self, path: Path, mode: str) -> str:
        pattern, options = self.discovery_options(mode)
        with tempfile.TemporaryDirectory() as temporary:
            files = [str(Path(temporary) / name) for name in ("capture", "status", "marker")]
            command = [
                "capture_bounded_command", *files, "", self.rg,
                "-nP", "-H", "--color", "never", *options, pattern, "--", str(path),
            ]
            script = (
                "E2E_SMELL_MAX_RULE_HITS=5\nE2E_SMELL_MAX_RULE_BYTES=100000\n"
                + scanner_function(self.source, "capture_bounded_command")
                + shlex.join(command)
                + '\nprintf "BOUND=%s\\n" "$BOUNDED_LIMIT_KIND"\n'
            )
            result = self.shell(script)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

    def test_non_emitting_windows_do_not_consume_rule_budget(self) -> None:
        path = self.fixture("request.catch(() => backup())\n" * 20)
        for mode in ("fallback", "parameterized"):
            with self.subTest(mode=mode):
                self.assertEqual(self.discover(path, mode), [])
                self.assertEqual(self.bounded(path, mode), "BOUND=")

    def test_same_line_earlier_comment_spliced_catch_keeps_whole_line(self) -> None:
        for mode, callback in (
            ("fallback", "() => backup()"),
            ("parameterized", "error => recover(error)"),
        ):
            with self.subTest(mode=mode):
                source = f"first.ca/* splice */tch({callback}); second.catch(handler);\n"
                path = self.fixture(source)
                hits = self.discover(path, mode)
                self.assertEqual(hits, [f"{path}:1:{source.rstrip()}"])
                self.assertTrue(self.accepted(hits[0], mode))

    def test_later_window_catch_preserves_earlier_candidate(self) -> None:
        for mode, callback in (
            ("fallback", "() => backup()"),
            ("parameterized", "error => recover(error)"),
        ):
            with self.subTest(mode=mode):
                path = self.fixture(
                    "first.catch(handler)\n" + "\n" * 11 + f"second.catch({callback});\n"
                )
                first_hit = f"{path}:1:first.catch(handler)"
                self.assertIn(first_hit, self.discover(path, mode))
                self.assertTrue(self.accepted(first_hit, mode))

    def test_multiline_and_spliced_callback_tokens_survive(self) -> None:
        fixtures = [
            ("fallback", "first.catch(\n ()\n =/* comment */> backup()\n);\n"),
            ("parameterized", "first.catch(\n error // comment\n => recover(error)\n);\n"),
            ("fallback", "first.catch(fun/* comment */ction () { return backup() });\n"),
            ("parameterized", "first.catch(function (error) { return recover(error) });\n"),
        ]
        for mode, source in fixtures:
            with self.subTest(mode=mode, source=source):
                path = self.fixture(source)
                first_hit = f"{path}:1:{source.splitlines()[0]}"
                self.assertIn(first_hit, self.discover(path, mode))
                self.assertTrue(self.accepted(first_hit, mode))

    def test_plain_positives_and_actual_overflow_remain(self) -> None:
        for mode, callback in (
            ("fallback", "() => backup()"),
            ("parameterized", "error => recover(error)"),
        ):
            with self.subTest(mode=mode):
                path = self.fixture(f"first.catch({callback});\n" * 20)
                hits = self.discover(path, mode)
                self.assertEqual(len(hits), 20)
                self.assertTrue(self.accepted(hits[0], mode))
                self.assertEqual(self.bounded(path, mode), "BOUND=hits")

    def test_thirteenth_following_line_does_not_extend_guard(self) -> None:
        path = self.fixture(
            "first.catch(handler)\n" + "\n" * 12 + "second.catch(() => backup());\n"
        )
        hits = self.discover(path, "fallback")
        self.assertNotIn(f"{path}:1:first.catch(handler)", hits)
        self.assertIn(f"{path}:14:second.catch(() => backup());", hits)

    def test_empty_callback_is_conservatively_retained(self) -> None:
        # Its semicolon satisfies discovery, while the unchanged classifier
        # still rejects an empty fallback callback.
        path = self.fixture("first.catch(() => {});\n")
        hits = self.discover(path, "fallback")
        self.assertEqual(len(hits), 1)
        self.assertFalse(self.accepted(hits[0], "fallback"))

    def test_assertion_terminators_without_semicolon_keep_catches(self) -> None:
        terminators = [
            "expect(value).toBeTruthy()",
            "expect(value).toBeDefined()",
            "expect(value).toBeNull()",
            "expect(value).toBeUndefined()",
            "expect(value).not.to.equal(null)",
            "expect(value).not.to.be.undefined",
            "expect(value).n/* join */ot.to.be.null",
        ]
        for terminator in terminators:
            with self.subTest(terminator=terminator):
                path = self.fixture(f"first.catch(() => backup())\n{terminator}\n")
                first_hit = f"{path}:1:first.catch(() => backup())"
                self.assertIn(first_hit, self.discover(path, "fallback"))
                self.assertTrue(self.accepted(first_hit, "fallback"))

    def test_catch_token_at_line_end_preserves_single_line_evidence(self) -> None:
        path = self.fixture("first.catch\n(() => backup());\n")
        first_hit = f"{path}:1:first.catch"
        self.assertEqual(self.discover(path, "fallback"), [first_hit])
        self.assertTrue(self.accepted(first_hit, "fallback"))

    def test_prior_block_comment_state_and_trailing_line_comment_survive(self) -> None:
        path = self.fixture("/* prefix\nend */ first.catch(() => backup()); // tail\n")
        hits = self.discover(path, "fallback")
        self.assertEqual(hits, [f"{path}:2:end */ first.catch(() => backup()); // tail"])
        self.assertTrue(self.accepted(hits[0], "fallback"))

    def test_finally_filtered_and_unfiltered_classifier_positives_match(self) -> None:
        for statement, positive in (
            ('try {} finally { return; };', True),
            ('try {} finally { re/**/turn; };', True),
            ('try {} finally { ret/* join */urn; };', True),
            ('try {} finally { café(); return; };', True),
            ('try {} finally { cleanup(); };', False),
            ('try {} finally { "return"; };', False),
            ('try {} finally { ret\\u0075rn; };', False),
        ):
            with self.subTest(statement=statement):
                path = self.fixture('await expect(page.locator("x")).toBeVisible();\n'
                                    + statement + '\n')
                original = self.discover(path, 'finally-return', unfiltered=True)
                filtered = self.discover(path, 'finally-return')
                self.assertEqual(original, [f'{path}:2:{statement}'])
                old_accepted = [hit for hit in original if self.accepted(hit, 'finally-return')]
                new_accepted = [hit for hit in filtered if self.accepted(hit, 'finally-return')]
                self.assertEqual(bool(old_accepted), positive)
                self.assertEqual(new_accepted, old_accepted)
                self.assertTrue(set(filtered) <= set(original))

    def test_finally_classifier_preserves_inclusive_window_boundary(self) -> None:
        for following, positive in ((12, True), (13, False)):
            with self.subTest(following=following):
                path = self.fixture('await expect(page.locator("x")).toBeVisible();\n'
                                    + 'try {} finally {\n' + '\n' * (following - 1)
                                    + 'return;\n};\n')
                original = self.discover(path, 'finally-return', unfiltered=True)
                filtered = self.discover(path, 'finally-return')
                self.assertEqual(len(original), 1)
                self.assertEqual(self.accepted(original[0], 'finally-return'), positive)
                self.assertEqual(
                    [hit for hit in filtered if self.accepted(hit, 'finally-return')],
                    original if positive else [],
                )

    def test_finally_discovery_keeps_invalid_oversized_body(self) -> None:
        path = self.fixture('')
        path.write_bytes(
            b'await expect(page.locator("x")).toBeVisible();\n'
            b'try {} finally {\n' + b'\xff' * 65537 + b'\nreturn; };\n'
        )
        original = self.discover(path, 'finally-return', unfiltered=True)
        self.assertEqual(len(original), 1)
        self.assertTrue(self.accepted(original[0], 'finally-return'))
        self.assertEqual(self.discover(path, 'finally-return'), original)

    def test_finally_raw_candidates_still_enforce_overflow(self) -> None:
        retained = self.fixture('try {} finally { re/**/turn; };\n' * 20)
        self.assertEqual(len(self.discover(retained, 'finally-return')), 20)
        self.assertEqual(self.bounded(retained, 'finally-return'), 'BOUND=hits')


if __name__ == "__main__":
    unittest.main()

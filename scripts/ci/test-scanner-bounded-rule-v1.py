#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Current Node reporting plus isolated legacy shell rule-cap regressions.

NodeBoundedReportTests checks complete canonical reports, retained source
anchors, parse failures and explicit rejection of the retired shell hit cap.
LegacyBoundedRuleTests alone checks the frozen shell truncation mechanism;
its success does not establish that Node implements configurable per-rule caps.

Historical failure: one noisy rule destroyed the whole shell scan.

Found by running the scanner over public repositories at pinned commits: on
sweetalert2 (18k stars) the shipped `#15` check exceeded
`E2E_SMELL_MAX_RULE_HITS` and the scan exited 2 having printed no Summary at
all. react-router behaved the same way. A user pointing `scan.sh` at an
ordinary Playwright repository got nothing back — not a partial result, not a
list of what did run, nothing.

The bounded limit itself is right: an unbounded rule could stream forever. What
was wrong is the blast radius. A truncated rule must disqualify itself, not the
other twenty-odd checks that completed normally.

The result must still fail closed — exit stays 2 and the truncated rule is
named — because a scan with a suppressed rule is not authoritative and must
never read as clean.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.legacy_scanner_oracle import legacy_scanner_file


ROOT = Path(__file__).resolve().parents[2]
SCAN = ROOT / "skills/e2e-reviewer/scripts/scan.sh"


def legacy_scan(files: dict[str, str], env: dict[str, str] | None = None):
    with tempfile.TemporaryDirectory() as tmp:
        for name, content in files.items():
            path = Path(tmp) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        result = subprocess.run(
            ["/bin/bash", "-p", str(legacy_scanner_file()), tmp],
            capture_output=True,
            text=True,
            env={**os.environ, "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                 "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                 "E2E_SMELL_ALLOW_PROJECT_ESLINT": "0", **(env or {})},
            timeout=300,
        )
    return result


def noisy_tree(files: int, per_file: int) -> dict[str, str]:
    """Many unawaited Playwright expects: the shape that tripped #15 in the field."""
    header = "import { test, expect } from '@playwright/test';\n\n"
    out = {}
    for index in range(files):
        body = "\n".join(
            f"test('case {index}_{n}', async ({{ page }}) => {{\n"
            f"  expect(page.getByTestId('x{n}')).toBeVisible();\n}});"
            for n in range(per_file)
        )
        out[f"tests/gen{index}.spec.ts"] = header + body
    return out


class LegacyBoundedRuleTests(unittest.TestCase):
    """Frozen shell cap/backend mechanism only; these do not establish Node coverage."""
    def test_assertion_candidates_keep_multiline_and_comment_split_matchers(self) -> None:
        header = "import { test, expect } from '@playwright/test';\n"
        noise = "expect(value).toEqual(1);\n" * 40
        for matcher, expected in (
            ("toBeTruthy", "[P0] #4f Locator always-true assertion"),
            ("toBeVisible", "#15 Missing await on Playwright expect"),
            ("toBe/* split identifier */Truthy", "[P0] #4f Locator always-true assertion"),
        ):
            with self.subTest(matcher=matcher):
                source = (
                    header + noise
                    + "test('real', async ({ page }) => {\n"
                    + "  expect(page.getByTestId('real'))\n"
                    + "\n" * 11 + f"    .{matcher}();\n"
                    + "});\n"
                )
                result = legacy_scan({"tests/real.spec.ts": source}, {
                    "E2E_SMELL_MAX_RULE_HITS": "15",
                    "E2E_SMELL_DISABLE_AST_GREP": "1",
                })
                out = result.stdout + result.stderr
                self.assertNotIn("INCOMPLETE", out)
                self.assertIn(expected, out)
                self.assertIn("real.spec.ts:43:", out)

    def test_foreign_source_cannot_exhaust_an_e2e_rule_budget(self) -> None:
        files = {
            "unit.spec.ts": (
                "import { expect } from 'vitest';\n"
                + "expect(value).toBeTruthy();\n" * 20
            ),
            "tests/real.spec.ts": (
                "import { test, expect } from '@playwright/test';\n"
                "test('real', async ({ page }) => {\n"
                "  expect(page.getByTestId('real')).toBeTruthy();\n"
                "});\n"
            ),
        }
        result = legacy_scan(files, {
            "E2E_SMELL_MAX_RULE_HITS": "5", "E2E_SMELL_DISABLE_AST_GREP": "1",
        })
        out = result.stdout + result.stderr
        self.assertNotIn("INCOMPLETE", out)
        self.assertIn("[P0] #4f Locator always-true assertion", out)
        self.assertIn("real.spec.ts:3:", out)
        self.assertEqual(result.returncode, 1)

    def test_cypress_calls_cannot_exhaust_a_playwright_rule_budget(self) -> None:
        files = {
            "tests/cypress.cy.ts": "expect(value).to.equal(1);\n" * 20,
            "tests/real.spec.ts": (
                "import { test, expect } from '@playwright/test';\n"
                "test('real', async ({ page }) => {\n"
                "  expect(page.getByTestId('real')).toBeVisible();\n"
                "});\n"
            ),
        }
        result = legacy_scan(files, {
            "E2E_SMELL_MAX_RULE_HITS": "5", "E2E_SMELL_DISABLE_AST_GREP": "1",
        })
        out = result.stdout + result.stderr
        self.assertNotRegex(out, r"INCOMPLETE: Tier 3 #15 ")
        self.assertIn("#15 Missing await on Playwright expect", out)
        self.assertIn("real.spec.ts:3:", out)

    def test_a_truncated_rule_still_leaves_a_summary(self) -> None:
        # Cap deliberately tiny so the tree is small and the test stays fast.
        result = legacy_scan(noisy_tree(6, 10), {"E2E_SMELL_MAX_RULE_HITS": "5"})
        out = result.stdout + result.stderr

        # The counts must appear, but never under a bare `Summary:` label.
        # That exact string is reserved for runs where every rule completed, so
        # a reader grepping for it cannot pick up partial counts as whole ones.
        self.assertRegex(
            out, r"(?m)^Summary \[INCOMPLETE",
            "a truncated rule must not suppress the counts for every other check",
        )
        self.assertNotRegex(
            out, r"(?m)^Summary:",
            "a bare `Summary:` must mean every rule ran",
        )
        self.assertIn(
            "INCOMPLETE", out,
            "the truncated rule must still be reported as incomplete",
        )
        self.assertEqual(
            result.returncode, 2,
            "a scan with a suppressed rule is not authoritative and must fail closed",
        )

    def test_the_suppressed_count_matches_the_named_rules(self) -> None:
        """The number in the label must be the number of rules that went silent.

        It was not. `printf '%s' $SUPPRESSED_RULES` reuses the format for every
        argument and concatenates them, so "#7 #15 #15" became "#7#15#15" and
        `wc -w` reported one rule suppressed when three were. The earlier tests
        here missed it because they assert the label exists and names a rule,
        never that its count is right -- a check on the presence of a claim
        rather than on its truth, which is the exact defect class this scanner
        exists to find.
        """
        result = legacy_scan(noisy_tree(6, 10), {"E2E_SMELL_MAX_RULE_HITS": "5"})
        out = result.stdout + result.stderr

        label = re.search(r"Summary \[INCOMPLETE — (\d+) rule\(s\) suppressed\]", out)
        self.assertIsNotNone(label, "the incomplete label must carry a count")

        listed = re.search(
            r"INCOMPLETE: these rules hit a bounded limit and reported nothing:(.*)",
            out,
        )
        self.assertIsNotNone(listed, "the suppressed rules must be listed by id")
        named = listed.group(1).split()
        self.assertGreater(len(named), 1, "this fixture must suppress several rules")
        self.assertEqual(
            int(label.group(1)), len(named),
            "the label's count must equal the number of rules listed below it",
        )
        self.assertEqual(
            len(named), len(set(named)),
            "a rule id checked by several patterns is still one suppressed rule",
        )

    def test_a_rule_id_shared_by_several_checks_is_counted_once(self) -> None:
        shapes = ("toBeTruthy()", "toBeDefined()", "not.toBeNull()", "not.toBeUndefined()")
        body = "\n".join(
            f"test('always true {n}', async ({{ page }}) => {{\n"
            f"  expect(page.locator('#a{n}')).{shape};\n"
            f"  expect(page.locator('#b{n}')).{shape};\n}});"
            for n, shape in enumerate(shapes)
        )
        files = {
            "tests/truthy.spec.ts": "import { test, expect } from '@playwright/test';\n\n" + body
        }
        result = legacy_scan(files, {"E2E_SMELL_MAX_RULE_HITS": "1"})
        out = result.stdout + result.stderr
        listed = re.search(
            r"INCOMPLETE: these rules hit a bounded limit and reported nothing:(.*)",
            out,
        )
        self.assertIsNotNone(listed, out)
        named = listed.group(1).split()
        self.assertIn("#4f", named, out)
        self.assertEqual(len(named), len(set(named)), out)
        label = re.search(r"Summary \[INCOMPLETE — (\d+) rule\(s\) suppressed\]", out)
        self.assertIsNotNone(label, out)
        self.assertEqual(int(label.group(1)), len(named), out)

    def test_the_truncated_rule_is_named(self) -> None:
        result = legacy_scan(noisy_tree(6, 10), {"E2E_SMELL_MAX_RULE_HITS": "5"})
        out = result.stdout + result.stderr
        self.assertRegex(
            out, r"INCOMPLETE.*#\d+",
            "the user needs to know which rule was suppressed, not just that one was",
        )

    def test_other_rules_still_report(self) -> None:
        files = noisy_tree(6, 10)
        # A distinct, low-volume smell that a working scan should still surface.
        files["tests/only.spec.ts"] = (
            "import { test, expect } from '@playwright/test';\n\n"
            "test.only('focused', async ({ page }) => {\n"
            "  await expect(page.getByTestId('a')).toBeVisible();\n});\n"
        )
        result = legacy_scan(files, {"E2E_SMELL_MAX_RULE_HITS": "5"})
        out = result.stdout + result.stderr
        self.assertIn(
            "#7", out,
            "checks that completed must still report; one noisy rule cannot mute them",
        )

    def test_rejected_raw_candidates_do_not_hide_early_or_late_valid_hits(self) -> None:
        """The rule budget belongs to classified findings, not regex candidates.

        The #7 discovery regex intentionally casts a wider net than the semantic
        predicate.  If the raw stream consumes the finding budget, ordinary
        methods whose names merely begin with ``only`` can suppress both an
        already-seen focused test and another valid hit later in path order.
        """
        noise = "\n".join(
            f"helper.onlyProperty{index}();" for index in range(8)
        )
        result = legacy_scan({
            "tests/a-early.spec.ts": (
                "import { test, expect } from '@playwright/test';\n"
                "test.only('early', async () => {});\n"
            ),
            "tests/m-noise.spec.ts": (
                "import { test, expect } from '@playwright/test';\n"
                f"{noise}\n"
            ),
            "tests/z-late.spec.ts": (
                "import { test, expect } from '@playwright/test';\n"
                "test.only('late', async () => {});\n"
            ),
        }, {
            "E2E_SMELL_MAX_RULE_HITS": "5",
            "E2E_SMELL_DISABLE_AST_GREP": "1",
        })
        out = result.stdout + result.stderr

        self.assertNotIn("INCOMPLETE", out)
        self.assertIn("a-early.spec.ts:2:", out)
        self.assertIn("z-late.spec.ts:2:", out)
        self.assertIn("#7 Focused test committed (2 hits)", out)
        self.assertEqual(result.returncode, 1)

    def test_classified_focused_hit_overflow_remains_incomplete(self) -> None:
        files = {
            f"tests/focused-{index}.spec.ts": (
                "import { test } from '@playwright/test';\n"
                f"test.only('case {index}', async () => {{}});\n"
            )
            for index in range(6)
        }
        result = legacy_scan(files, {
            "E2E_SMELL_MAX_RULE_HITS": "5",
            "E2E_SMELL_DISABLE_AST_GREP": "1",
        })
        out = result.stdout + result.stderr

        self.assertRegex(out, r"INCOMPLETE: Tier 3 #7 ")
        self.assertIn("these rules hit a bounded limit and reported nothing: #7", out)
        self.assertEqual(result.returncode, 2)

    def test_consumed_actions_do_not_hide_early_or_late_number_16_candidates(self) -> None:
        """The #16 budget applies after its three semantic classifications."""
        awaited = "\n".join(
            (
                f"  await page.getByTestId('safe-{index}').click();"
                if index % 2 == 0
                else f"  await page.getByTestId('safe-{index}')\n    .click();"
            )
            for index in range(8)
        )
        result = legacy_scan({
            "tests/actions.spec.ts": (
                "import { test } from '@playwright/test';\n"
                "test('actions', async ({ page }) => {\n"
                "  const early = page.getByTestId('early').click();\n"
                f"{awaited}\n"
                "  page.getByTestId('direct').click();\n"
                "  const button = page.getByTestId('late');\n"
                "  button.click();\n"
                "});\n"
            ),
        }, {
            "E2E_SMELL_MAX_RULE_HITS": "5",
            "E2E_SMELL_DISABLE_AST_GREP": "1",
        })
        out = result.stdout + result.stderr

        self.assertNotRegex(out, r"INCOMPLETE: Tier 3 #16 ")
        self.assertIn("Possible deferred/discarded Playwright action promise", out)
        self.assertIn("Missing await on Playwright action", out)
        self.assertIn("Possible missing await on Locator/POM action", out)
        self.assertIn("early').click", out)
        self.assertIn("direct').click", out)
        self.assertIn("button.click", out)
        self.assertEqual(result.returncode, 0)

    def test_classified_number_16_hit_overflow_remains_incomplete(self) -> None:
        fixtures = {
            "direct": (
                "Missing await on Playwright action",
                "\n".join(
                    f"  page.getByTestId('unsafe-{index}').click();"
                    for index in range(6)
                ),
            ),
            "deferred": (
                "Possible deferred/discarded Playwright action promise",
                "\n".join(
                    f"  const pending{index} = page.getByTestId('unsafe-{index}').click();"
                    for index in range(6)
                ),
            ),
            "variable": (
                "Possible missing await on Locator/POM action",
                "\n".join(
                    f"  button{index}.click();"
                    for index in range(6)
                ),
            ),
        }
        for mode, (title, actions) in fixtures.items():
            with self.subTest(mode=mode):
                declarations = ""
                if mode == "variable":
                    declarations = "\n".join(
                        f"  const button{index} = page.getByTestId('unsafe-{index}');"
                        for index in range(6)
                    ) + "\n"
                result = legacy_scan({
                    "tests/actions.spec.ts": (
                        "import { test } from '@playwright/test';\n"
                        "test('actions', async ({ page }) => {\n"
                        f"{declarations}{actions}\n"
                        "});\n"
                    ),
                }, {
                    "E2E_SMELL_MAX_RULE_HITS": "5",
                    "E2E_SMELL_DISABLE_AST_GREP": "1",
                })
                out = result.stdout + result.stderr

                self.assertIn(f"INCOMPLETE: Tier 3 #16 {title} ", out)
                self.assertIn(
                    "these rules hit a bounded limit and reported nothing: #16",
                    out,
                )
                self.assertEqual(result.returncode, 2)

    def test_an_unbounded_scan_is_unaffected(self) -> None:
        result = legacy_scan({
            "tests/a.spec.ts": (
                "import { test, expect } from '@playwright/test';\n\n"
                "test.only('focused', async ({ page }) => {\n"
                "  await expect(page.getByTestId('a')).toBeVisible();\n});\n"
            )
        })
        out = result.stdout + result.stderr
        self.assertNotIn("INCOMPLETE", out)
        self.assertRegex(out, r"(?m)^Summary:")
        self.assertEqual(result.returncode, 1, "a P0 finding still exits 1")


def scan(files: dict[str, str], env: dict[str, str] | None = None):
    """Current product: no retired backend/limit controls are inherited."""
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        for name, content in files.items():
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content, encoding="utf-8")
        environment = {key: value for key, value in os.environ.items() if not key.startswith("E2E_SMELL_")}
        result = subprocess.run(
            ["/bin/bash", "-p", str(SCAN), raw, "--format", "json"],
            capture_output=True, text=True, timeout=300, env={**environment, **(env or {})},
        )
        for name, content in files.items():
            if (root / name).read_text(encoding="utf-8") != content:
                raise AssertionError("scanner changed original fixture bytes")
    return result


class NodeBoundedReportTests(unittest.TestCase):
    def complete(self, result, exit_code):
        self.assertEqual(result.returncode, exit_code, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertEqual(report["schema"], "e2e-skills-node-scan-v1")
        self.assertEqual(report["status"], "COMPLETE")
        self.assertIs(report["execution"]["complete"], True)
        self.assertEqual(report["execution"]["exitCode"], exit_code)
        self.assertEqual(report["execution"]["diagnostics"], [])
        return report

    def test_retired_limit_is_rejected_instead_of_silently_ignored(self):
        result = scan(noisy_tree(6, 10), {"E2E_SMELL_MAX_RULE_HITS": "5"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("INCOMPLETE: retired E2E_SMELL_", result.stdout + result.stderr)
        self.assertNotRegex(result.stdout + result.stderr, r"(?m)^Summary:")

    def test_original_noisy_tree_retains_all_findings_and_an_independent_rule(self):
        files = noisy_tree(6, 10)
        files["tests/only.spec.ts"] = (
            "import { test, expect } from '@playwright/test';\n\n"
            "test.only('focused', async ({ page }) => {\n"
            "  await expect(page.getByTestId('a')).toBeVisible();\n});\n"
        )
        report = self.complete(scan(files), 1)
        self.assertEqual(len([hit for hit in report["findings"] if hit["patternId"] == "#15"]), 60)
        self.assertEqual([(hit["patternId"], hit["line"]) for hit in report["findings"] if hit["patternId"] == "#7"], [("#7", 3)])

    def test_original_multiline_matchers_keep_their_source_anchors(self):
        header = "import { test, expect } from '@playwright/test';\n"
        noise = "expect(value).toEqual(1);\n" * 40
        for matcher, pattern, exit_code in [("toBeTruthy", "#4f", 1), ("toBeVisible", "#15", 0)]:
            with self.subTest(matcher=matcher):
                source = (header + noise + "test('real', async ({ page }) => {\n"
                          + "  expect(page.getByTestId('real'))\n" + "\n" * 11 + f"    .{matcher}();\n" + "});\n")
                report = self.complete(scan({"tests/real.spec.ts": source}), exit_code)
                self.assertIn((pattern, 43), [(hit["patternId"], hit["line"]) for hit in report["findings"]])

    def test_original_split_identifier_is_a_parse_error_not_a_clean_scan(self):
        # Preserve historical bytes. A comment between identifier fragments
        # does not make valid JavaScript; lexical shell recovery is legacy only.
        source = ("import { test, expect } from '@playwright/test';\n" + "expect(value).toEqual(1);\n" * 40
                  + "test('real', async ({ page }) => {\n  expect(page.getByTestId('real'))\n"
                  + "\n" * 11 + "    .toBe/* split identifier */Truthy();\n});\n")
        result = scan({"tests/real.spec.ts": source})
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertIs(report["execution"]["complete"], False)
        self.assertTrue(report["execution"]["diagnostics"])
        self.assertTrue(any("parse" in str(item).lower() for item in report["execution"]["diagnostics"]))

    def test_foreign_and_cypress_noise_cannot_hide_playwright_findings(self):
        for name, noise, matcher, pattern, exit_code in [
            ("unit.spec.ts", "import { expect } from 'vitest';\n" + "expect(value).toBeTruthy();\n" * 20, "toBeTruthy", "#4f", 1),
            ("tests/cypress.cy.ts", "expect(value).to.equal(1);\n" * 20, "toBeVisible", "#15", 0),
        ]:
            with self.subTest(name=name):
                source = ("import { test, expect } from '@playwright/test';\n"
                          + "test('real', async ({ page }) => {\n"
                          + f"  expect(page.getByTestId('real')).{matcher}();\n" + "});\n")
                report = self.complete(scan({name: noise, "tests/real.spec.ts": source}), exit_code)
                self.assertEqual([(hit["patternId"], hit["line"]) for hit in report["findings"]], [(pattern, 3)])

    def test_rejected_focused_candidates_cannot_hide_early_or_late_hits(self):
        noise = "\n".join(f"helper.onlyProperty{index}();" for index in range(8))
        files = {
            "tests/a-early.spec.ts": (
                "import { test, expect } from '@playwright/test';\n"
                "test.only('early', async () => {});\n"),
            "tests/m-noise.spec.ts": (
                "import { test, expect } from '@playwright/test';\n" + noise + "\n"),
            "tests/z-late.spec.ts": (
                "import { test, expect } from '@playwright/test';\n"
                "test.only('late', async () => {});\n"),
        }
        report = self.complete(scan(files), 1)
        self.assertEqual([(Path(hit["file"]).name, hit["line"], hit["patternId"])
                          for hit in report["findings"]],
                         [("a-early.spec.ts", 2, "#7"), ("z-late.spec.ts", 2, "#7")])

    def test_consumed_actions_keep_early_direct_and_variable_anchors(self):
        awaited = "\n".join(
            (f"  await page.getByTestId('safe-{index}').click();" if index % 2 == 0
             else f"  await page.getByTestId('safe-{index}')\n    .click();") for index in range(8))
        source = ("import { test } from '@playwright/test';\n"
                  "test('actions', async ({ page }) => {\n"
                  "  const early = page.getByTestId('early').click();\n"
                  + awaited + "\n  page.getByTestId('direct').click();\n"
                  "  const button = page.getByTestId('late');\n  button.click();\n});\n")
        report = self.complete(scan({"tests/actions.spec.ts": source}), 0)
        hits = [hit for hit in report["findings"] if hit["patternId"] == "#16"]
        self.assertEqual([(hit["line"], hit["disposition"]) for hit in hits], [(3, "candidate"), (16, "confirmed"), (18, "candidate")])


if __name__ == "__main__":
    unittest.main(verbosity=2)

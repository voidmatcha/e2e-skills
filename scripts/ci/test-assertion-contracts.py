#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Dependency-free guards for contract-preserving reviewer replacements.

Live semantic checks of the extracted table run separately via
scripts/evals/run-assertion-contract-probes.cjs.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
REFS = ROOT / "skills/e2e-reviewer/references"


class AssertionContracts(unittest.TestCase):
    def test_raw_predicates_are_preserved_in_both_surfaces(self):
        for filename, receiver, value in [
            ("applying-fixes.md", "x", "v"),
            ("pattern-reference.md", "el", "x"),
        ]:
            text = (REFS / filename).read_text()
            for read, matcher in [("textContent", "toBe"), ("allTextContents", "toContain")]:
                with self.subTest(filename=filename, read=read):
                    expected = f"await expect.poll(() => {receiver}.{read}()).{matcher}({value})"
                    self.assertTrue(expected in text, f"{filename}: missing {expected}")

    def test_compound_visibility_retains_or(self):
        text = (REFS / "pattern-reference.md").read_text()
        row = next(line for line in text.splitlines() if "**Compound boolean expression**" in line)
        self.assertIn("await expect.poll(async () => (await a.isVisible()) || (await b.isVisible())).toBe(true)", row)
        self.assertNotIn("page.locator('.a, .b')", row)

    def test_rendered_text_substring_keeps_its_source_and_matcher(self):
        text = (REFS / "applying-fixes.md").read_text()
        row = next(line for line in text.splitlines()
                   if "expect(await x.innerText()).toContain(v)" in line)
        self.assertIn("await expect.poll(() => x.innerText()).toContain(v)", row)
        self.assertNotIn("toContainText", row)

    def test_cypress_query_existence_is_not_removed_by_each(self):
        text = (REFS / "pattern-reference.md").read_text()
        self.assertFalse("`cy.get('body').find('.row').each(...)` after a passing parent" in text)
        self.assertTrue("cy.wrap([]).each" in text)
        self.assertTrue("implicit existence" in text)

    def test_snapshot_and_actionability_are_not_temporal_or_visibility_proofs(self):
        text = (REFS / "applying-fixes.md").read_text()
        for bad in ["scrollIntoView ensures interactability", "Visibility check covers force's purpose", 'Snapshot-of-absence semantic ("never appeared")', "Adding `await` makes it auto-retry"]:
            with self.subTest(bad=bad):
                self.assertFalse(bad in text, f"Unsafe guidance remains: {bad}")

    def test_scanner_candidates_do_not_replace_semantic_review(self):
        text = (REFS / "applying-fixes.md").read_text()
        self.assertTrue("Scanner hits are candidates, not verdicts" in text)
        self.assertFalse("If the line isn't flagged, leave it alone" in text)

    def test_conditional_rtl_fix_resolves_to_complete_reference(self):
        applying = (REFS / "applying-fixes.md").read_text()
        route = re.search(
            r"Before proposing or applying any `#4f` fix for an "
            r"RTL/Testing-Library helper.*?\[`rtl-jest-dom-fixes\.md`\]"
            r"\(([^)]+)\)",
            applying,
        )
        self.assertIsNotNone(route, "missing conditional RTL reference route")
        reference = REFS / route.group(1)
        self.assertTrue(reference.is_file(), f"missing routed reference: {reference}")

        details = reference.read_text()
        exact_row = (
            "| `#4f` `expect(screen.getBy*(...)).toBeTruthy()` | "
            "`expect(screen.getBy*(...)).toBeInTheDocument()` | "
            "jest-dom matcher — see prereq check below |"
        )
        self.assertNotIn(exact_row, applying)
        self.assertEqual(details.count(exact_row), 1)
        self.assertIn("`**§4.1 row:**` attribution", applying)
        self.assertIn("MANDATORY before bulk replacement", details)
        for required in (
            "Pure Jest/Vitest unit tests and Storybook interaction tests are out of scope",
            "setupFilesAfterEach",
            "setupFiles",
            "import '@testing-library/jest-dom';",
            "import '@testing-library/jest-dom/vitest';",
            "@types/testing-library__jest-dom",
        ):
            with self.subTest(required=required):
                self.assertIn(required, details)

        self.assertIn(
            'A positive `.toBeAttached()` is also meaningful when DOM attachment itself is the promised state.',
            applying,
        )


if __name__ == "__main__":
    unittest.main()

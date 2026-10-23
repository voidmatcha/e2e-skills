#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""#3 must see the `try/catch` swallow, not only the `.catch(() => {})` one.

A controlled ablation measured the reviewer at 6/6 on the one error-swallow
case the scanner could match and 0/6 or 1/6 on five cases it could not. File
count and file role did not separate them -- two of the missed cases were
single-file. The separator was whether Phase 1 produced a hit the reviewer had
to adjudicate. Rewording the contract twice changed nothing, because the
contract already forbade the shape; what was missing was the anchor.

These guards pin the detection and, just as importantly, the exclusions: a
catch that rethrows is not swallowing, and a swallow that reaches triage must
never reach the P0 exit gate, because `try/catch` has too many legitimate uses
for grep to decide.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCAN = ROOT / "skills/e2e-reviewer/scripts/scan.sh"

# Exact unsupported contexts in the unchanged legacy fixtures. These are
# incomplete analyses, never successful negative classifications. Keep them
# visible until propagation/provenance support is implemented and verified.
UNSUPPORTED_CATCHES = {
    "d.spec.ts": 180, "e.spec.ts": 178, "fn1-nested.spec.ts": 279,
    "fp4-sleep-only.spec.ts": 164, "h.spec.ts": 263, "i.spec.ts": 233,
    "k.spec.ts": 218, "comment-gate.spec.ts": 229,
    "string-brace.spec.ts": 280, "regex-brace.spec.ts": 301,
}


def scan(files: dict[str, str]) -> tuple[int, int, str]:
    """Preserve fixture assertions using the canonical current-product report.

    The returned P0 count is confirmed P0, even for an explicitly incomplete
    fixture. Candidate preservation and execution completeness are independent.
    """
    with tempfile.TemporaryDirectory() as tmp:
        for name, content in files.items():
            path = Path(tmp) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        before = {name: hashlib.sha256((Path(tmp) / name).read_bytes()).hexdigest()
                  for name in files}
        result = subprocess.run(
            ["/bin/bash", "-p", str(SCAN), tmp, "--format", "json", "--fail-on", "p0"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
            timeout=60,
        )
        assert before == {name: hashlib.sha256((Path(tmp) / name).read_bytes()).hexdigest()
                          for name in files}, "scanner changed original fixture bytes"
        report = json.loads(result.stdout)
        assert report["schema"] == "e2e-skills-node-scan-v1", result.stdout
        expected = sorted(("analysis-unknown", "catchHandlers", name, start)
                          for name, start in UNSUPPORTED_CATCHES.items() if name in files)
        actual = sorted((item["code"], item.get("detector"),
                         str(Path(item["file"]).relative_to(Path(tmp).resolve())), item.get("start"))
                        for item in report["execution"]["diagnostics"])
        assert actual == expected, result.stdout
        incomplete = bool(expected)
        assert report["status"] == ("INCOMPLETE" if incomplete else "COMPLETE"), result.stdout
        assert report["execution"]["complete"] is (not incomplete), result.stdout
        assert result.returncode == report["execution"]["exitCode"] == (2 if incomplete else 0), result.stdout
        assert bool(report["execution"]["incomplete"]) is incomplete, result.stdout
        assert not report.get("errors"), result.stdout
        findings = [item for item in report["findings"] if item["patternId"] == "#3"]
        assert report["counts"]["p0"] == 0, result.stdout
        assert all(item["disposition"] == "candidate" and item["severity"] == "P0"
                   for item in findings), result.stdout
        assert all(item["file"] in {str((Path(tmp) / name).resolve()) for name in files}
                   for item in findings), result.stdout
        assert all(0 <= item["start"] < item["end"] <= len(Path(item["file"]).read_text())
                   for item in findings), result.stdout
    out = result.stdout
    return len(findings), report["counts"]["p0"], out


SPEC_HEADER = "import { test, expect } from '@playwright/test';\n\n"


class TryCatchDetectionTests(unittest.TestCase):
    def test_flags_a_swallowed_readiness_gate(self) -> None:
        hits, p0, _ = scan({"a.spec.ts": SPEC_HEADER + """
test('shows the total', async ({ page }) => {
  await page.goto('/x');
  try {
    await page.getByTestId('saved').waitFor({ state: 'visible' });
  } catch (error) {
    console.warn('not confirmed', error);
  }
  await expect(page.getByTestId('total')).toHaveText('9');
});
"""})
        self.assertGreater(hits, 0, "swallowed readiness gate must be flagged")
        self.assertEqual(p0, 0, "try/catch is undecidable by grep: triage, not P0")

    def test_flags_a_swallowed_assertion_in_a_callback(self) -> None:
        hits, _, _ = scan({"b.spec.ts": SPEC_HEADER + """
test('sends the payload', async ({ page }) => {
  const sent = page.waitForRequest('**/api/x').then((request) => {
    try {
      expect(request.postDataJSON()).toEqual({ a: 1 });
    } catch (error) {
      console.log('skipped');
    }
  });
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await sent;
  await expect(page.getByTestId('receipt')).toHaveText('R-1');
});
"""})
        self.assertGreater(hits, 0)

    def test_flags_a_multiline_expect_poll(self) -> None:
        # A split chain is the normal formatting for expect.poll, and a
        # line-based check silently misses it.
        hits, _, _ = scan({"support/f.ts": """
import { test as base, expect } from '@playwright/test';

export const test = base.extend({
  seeded: async ({ page }, use) => {
    try {
      await expect
        .poll(async () => (await page.request.get('/s')).status())
        .toBe(200);
    } catch (error) {
      // seeded late
    }
    await use('ok');
  },
});
"""})
        self.assertGreater(hits, 0, "expect.poll split across lines must be seen")

    def test_flags_a_swallowed_hand_rolled_gate(self) -> None:
        hits, _, _ = scan({"c.cy.js": """
export function prime() {
  cy.get('[data-testid=status]').then(($s) => {
    try {
      if ($s.text() !== 'Synced') {
        throw new Error('not synced');
      }
    } catch (error) {
      cy.log('unconfirmed');
    }
  });
}
"""})
        self.assertGreater(hits, 0, "a throw the catch swallows is still a gate")

    def test_does_not_flag_a_rethrowing_catch(self) -> None:
        hits, p0, _ = scan({"d.spec.ts": SPEC_HEADER + """
test('handles the conflict', async ({ page }) => {
  try {
    await page.getByTestId('slot').waitFor({ state: 'visible' });
  } catch (error) {
    if (!(error instanceof SlotError)) {
      throw error;
    }
  }
  await expect(page.getByTestId('notice')).toHaveText('conflict');
});
"""})
        self.assertEqual(hits, 0, "a narrowed catch that rethrows is not a swallow")
        self.assertEqual(p0, 0)

    def test_does_not_flag_a_try_without_a_dependent_operation(self) -> None:
        hits, _, _ = scan({"e.spec.ts": SPEC_HEADER + """
test('reads config', async ({ page }) => {
  let parsed = {};
  try {
    parsed = JSON.parse(process.env.CONFIG || '{}');
  } catch (error) {
    parsed = {};
  }
  await page.goto('/x');
  await expect(page.getByTestId('name')).toHaveText(String(parsed.name));
});
"""})
        self.assertEqual(hits, 0, "a try around plain parsing suppresses no gate")


class TryCatchPairingTests(unittest.TestCase):
    """The catch is paired with its own try by brace balance; only its block can rethrow."""

    def test_flags_nested_try_inside_the_suppressed_region(self) -> None:
        hits, p0, _ = scan({"fn1-nested.spec.ts": SPEC_HEADER + "test('nested', async ({ page }) => {\n  await page.goto('/x');\n  try {\n    await page.getByTestId('saved').waitFor({ state: 'visible' });\n    let parsed = {};\n    try {\n      parsed = JSON.parse(process.env.CONFIG || '{}');\n    } catch {\n      parsed = {};\n    }\n    console.log(parsed);\n  } catch (error) {\n    console.warn('not confirmed', error);\n  }\n  await expect(page.getByTestId('total')).toHaveText('9');\n});\n"})
        self.assertGreater(hits, 0, "an inner try must not hide the outer catch's gate")
        self.assertEqual(p0, 0)

    def test_flags_try_body_longer_than_forty_lines(self) -> None:
        hits, p0, _ = scan({"fn2-far.spec.ts": SPEC_HEADER + "test('far', async ({ page }) => {\n  try {\n    await page.getByTestId('saved').waitFor({ state: 'visible' });\n    await page.getByTestId('f1').fill('v');\n    await page.getByTestId('f2').fill('v');\n    await page.getByTestId('f3').fill('v');\n    await page.getByTestId('f4').fill('v');\n    await page.getByTestId('f5').fill('v');\n    await page.getByTestId('f6').fill('v');\n    await page.getByTestId('f7').fill('v');\n    await page.getByTestId('f8').fill('v');\n    await page.getByTestId('f9').fill('v');\n    await page.getByTestId('f10').fill('v');\n    await page.getByTestId('f11').fill('v');\n    await page.getByTestId('f12').fill('v');\n    await page.getByTestId('f13').fill('v');\n    await page.getByTestId('f14').fill('v');\n    await page.getByTestId('f15').fill('v');\n    await page.getByTestId('f16').fill('v');\n    await page.getByTestId('f17').fill('v');\n    await page.getByTestId('f18').fill('v');\n    await page.getByTestId('f19').fill('v');\n    await page.getByTestId('f20').fill('v');\n    await page.getByTestId('f21').fill('v');\n    await page.getByTestId('f22').fill('v');\n    await page.getByTestId('f23').fill('v');\n    await page.getByTestId('f24').fill('v');\n    await page.getByTestId('f25').fill('v');\n    await page.getByTestId('f26').fill('v');\n    await page.getByTestId('f27').fill('v');\n    await page.getByTestId('f28').fill('v');\n    await page.getByTestId('f29').fill('v');\n    await page.getByTestId('f30').fill('v');\n    await page.getByTestId('f31').fill('v');\n    await page.getByTestId('f32').fill('v');\n    await page.getByTestId('f33').fill('v');\n    await page.getByTestId('f34').fill('v');\n    await page.getByTestId('f35').fill('v');\n    await page.getByTestId('f36').fill('v');\n    await page.getByTestId('f37').fill('v');\n    await page.getByTestId('f38').fill('v');\n    await page.getByTestId('f39').fill('v');\n    await page.getByTestId('f40').fill('v');\n    await page.getByTestId('f41').fill('v');\n    await page.getByTestId('f42').fill('v');\n  } catch (error) {\n    console.warn('not confirmed', error);\n  }\n  await expect(page.getByTestId('total')).toHaveText('9');\n});\n"})
        self.assertGreater(hits, 0, 'a long try body is still paired with its catch')
        self.assertEqual(p0, 0)

    def test_flags_throw_after_the_catch_block(self) -> None:
        hits, p0, _ = scan({"fn3-throw-after.spec.ts": SPEC_HEADER + "test('after', async ({ page }) => {\n  try {\n    await page.getByTestId('saved').waitFor({ state: 'visible' });\n  } catch (error) {\n    console.warn('not confirmed', error);\n  }\n  await expect(page.getByTestId('total')).toHaveText('9');\n});\n\nfunction mustExist(v: unknown) {\n  if (!v) throw new Error('missing');\n}\n"})
        self.assertGreater(hits, 0, 'a throw outside the catch block does not rethrow')
        self.assertEqual(p0, 0)

    def test_flags_allman_braces(self) -> None:
        hits, p0, _ = scan({"fn5-allman.spec.ts": SPEC_HEADER + "test('allman', async ({ page }) => {\n  try\n  {\n    await page.getByTestId('saved').waitFor({ state: 'visible' });\n  }\n  catch (error)\n  {\n    console.warn('not confirmed', error);\n  }\n  await expect(page.getByTestId('total')).toHaveText('9');\n});\n"})
        self.assertGreater(hits, 0, 'a brace on its own line still pairs try and catch')
        self.assertEqual(p0, 0)

    def test_does_not_flag_rethrow_after_long_logging(self) -> None:
        hits, _, _ = scan({"fp2-long-rethrow.spec.ts": SPEC_HEADER + "test('long rethrow', async ({ page }) => {\n  try {\n    await page.getByTestId('slot').waitFor({ state: 'visible' });\n  } catch (error) {\n    console.error('slot missing');\n    console.error('url', page.url());\n    console.error('title', await page.title());\n    console.error('a');\n    console.error('b');\n    console.error('c');\n    console.error('d');\n    console.error('e');\n    console.error('f');\n    console.error('g');\n    console.error('h');\n    console.error('i');\n    throw error;\n  }\n  await expect(page.getByTestId('notice')).toHaveText('x');\n});\n"})
        self.assertEqual(hits, 0, 'a rethrow anywhere in the catch block is not a swallow')

    def test_does_not_flag_sleep_only_try(self) -> None:
        hits, _, _ = scan({"fp4-sleep-only.spec.ts": SPEC_HEADER + "test('sleep only', async ({ page }) => {\n  await page.goto('/x');\n  try {\n    await page.waitForTimeout(200);\n  } catch {\n    // never\n  }\n  await expect(page.getByTestId('name')).toHaveText('n');\n});\n"})
        self.assertEqual(hits, 0, 'a bare waitForTimeout is a sleep, not a gate')

    def test_flags_a_checking_page_object_helper(self) -> None:
        hits, p0, _ = scan({"h.spec.ts": SPEC_HEADER + """
test('adds a client to the new organization', async ({ page }) => {
  try {
    await orgPage.organizationDropdownVisible();
    await orgPage.selectOrganization('Acme');
    await page.waitForTimeout(1500);
  } catch {
    // continue on the active organization
  }
  await clientsPage.addClient('Ada');
});
"""})
        self.assertGreater(hits, 0, "a helper named for a check hides the gate it swallows")
        self.assertEqual(p0, 0)

    def test_does_not_flag_an_is_read_or_a_sleep(self) -> None:
        hits, _, _ = scan({"i.spec.ts": SPEC_HEADER + """
test('closes the banner if shown', async ({ page }) => {
  let shown = false;
  try {
    shown = await page.getByRole('banner').isVisible();
    await page.waitForTimeout(200);
  } catch {
    shown = false;
  }
  await expect(page.getByRole('main')).toHaveText(shown ? 'a' : 'b');
});
"""})
        self.assertEqual(hits, 0, "an isX read never throws and a sleep is not a gate")

    def test_does_not_flag_a_destructured_rethrow(self) -> None:
        hits, _, _ = scan({"j.spec.ts": SPEC_HEADER + """
test('surfaces the save error', async ({ page }) => {
  try {
    await page.getByTestId('saved').waitFor({ state: 'visible' });
  } catch ({ message }) {
    throw new Error(`save not confirmed: ${message}`);
  }
  await expect(page.getByTestId('total')).toHaveText('9');
});
"""})
        self.assertEqual(hits, 0, "braces in a destructured catch parameter are not the catch block")

    def test_does_not_flag_a_plain_check_or_checkout_action(self) -> None:
        hits, _, _ = scan({"k.spec.ts": SPEC_HEADER + """
test('accepts the terms if offered', async ({ page }) => {
  try {
    await page.getByRole('checkbox', { name: 'Terms' }).check();
    await cartPage.checkout();
  } catch {
    // the terms box is optional
  }
  await expect(page.getByRole('heading', { name: 'Order placed' })).toBeVisible();
});
"""})
        self.assertEqual(hits, 0, "check() and checkout() are actions, not helpers named for a check")


class TryCatchLexedPairingTests(unittest.TestCase):
    """Pairing and matching run on lexed source: literals and comments are inert."""

    def test_flags_try_after_apostrophe_in_jsx_text(self) -> None:
        hits, p0, _ = scan({"jsx-apostrophe.spec.tsx": SPEC_HEADER + """test('renders after a warning', async ({ page }) => {
  const warning = <p>Don't panic</p>;
  console.log(warning);
  try {
    await expect(page.getByTestId('saved')).toBeVisible();
  } catch (error) {
    console.warn('not confirmed', error);
  }
});
"""})
        self.assertGreater(hits, 0, "an apostrophe in JSX text must not hide a swallowed assertion")
        self.assertEqual(p0, 0)

    def test_flags_when_catch_comment_mentions_throw(self) -> None:
        hits, p0, _ = scan({"comment-rethrow.spec.ts": SPEC_HEADER + """test('comment says throw but catch swallows', async ({ page }) => {
  await page.goto('/x');
  try {
    await page.getByTestId('saved').waitFor({ state: 'visible' });
  } catch (error) {
    // never throw here
    console.warn('not confirmed', error);
  }
  await expect(page.getByTestId('total')).toHaveText('9');
});
"""})
        self.assertGreater(hits, 0, "`throw` in a catch comment is not a rethrow")
        self.assertEqual(p0, 0)

    def test_does_not_flag_when_only_a_try_comment_mentions_throw(self) -> None:
        hits, _, _ = scan({"comment-gate.spec.ts": SPEC_HEADER + """test('comment mentions throw in try', async ({ page }) => {
  await page.goto('/x');
  try {
    // TODO: throw when the widget is missing
    await page.waitForTimeout(100);
  } catch (error) {
    console.warn('ignored', error);
  }
  await expect(page.getByTestId('total')).toHaveText('9');
});
"""})
        self.assertEqual(hits, 0, "`throw` in a try comment is not a gate the catch swallows")

    def test_flags_nested_try_with_brace_in_string(self) -> None:
        hits, p0, _ = scan({"string-brace.spec.ts": SPEC_HEADER + """test('brace inside a string in a nested try', async ({ page }) => {
  await page.goto('/x');
  try {
    await page.getByTestId('saved').waitFor({ state: 'visible' });
    try {
      await page.getByTestId('ok').fill('}');
    } catch (inner) {
      throw inner;
    }
  } catch (error) {
    console.warn('not confirmed', error);
  }
  await expect(page.getByTestId('total')).toHaveText('9');
});
"""})
        self.assertGreater(hits, 0, "a brace in a string must not pair the outer catch with the inner try")
        self.assertEqual(p0, 0)

    def test_flags_nested_try_with_brace_in_regex(self) -> None:
        hits, p0, _ = scan({"regex-brace.spec.ts": SPEC_HEADER + """test('brace inside a regex in a nested try', async ({ page }) => {
  await page.goto('/x');
  try {
    await page.getByTestId('saved').waitFor({ state: 'visible' });
    try {
      const m = /}/.test(await page.title());
      console.log(m);
    } catch (inner) {
      throw inner;
    }
  } catch (error) {
    console.warn('not confirmed', error);
  }
  await expect(page.getByTestId('total')).toHaveText('9');
});
"""})
        self.assertGreater(hits, 0, "a brace in a regex literal must not pair the outer catch with the inner try")
        self.assertEqual(p0, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

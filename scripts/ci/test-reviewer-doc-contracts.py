#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Static guards for reviewer fix guidance and conditional-bypass scope."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SECURITY = ROOT / "SECURITY.md"
SKILL = ROOT / "skills" / "e2e-reviewer" / "SKILL.md"
PATTERN_REFERENCE = (
    ROOT / "skills" / "e2e-reviewer" / "references" / "pattern-reference.md"
)
GREP_PATTERNS = (
    ROOT / "skills" / "e2e-reviewer" / "references" / "grep-patterns.md"
)
APPLYING_FIXES = (
    ROOT / "skills" / "e2e-reviewer" / "references" / "applying-fixes.md"
)
EVALS = ROOT / "skills" / "e2e-reviewer" / "evals" / "evals.json"
SCANNER = ROOT / "skills" / "e2e-reviewer" / "scripts" / "scan.sh"
VERIFICATION_RULES = (
    ROOT / "skills" / "e2e-reviewer" / "references" / "verification-rules.md"
)
README = ROOT / "README.md"
TRANSLATED_READMES = (
    ROOT / "README.ko.md",
    ROOT / "README.ja.md",
    ROOT / "README.zh-cn.md",
)


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def source_line_number(source: str, needle: str) -> int:
    matches = [
        line_number
        for line_number, line in enumerate(source.splitlines(), start=1)
        if needle in line
    ]
    assert len(matches) == 1, (
        f"expected one fixture line containing {needle!r}, found {matches}"
    )
    return matches[0]


def require_contract(surface: str, contract: str, name: str) -> None:
    assert contract in surface, f"{name} missing contract: {contract}"


def scanner_extensions(scanner_source: str) -> tuple[str, ...]:
    match = re.search(
        r"^CODE_EXTENSIONS='([^']+)'$",
        scanner_source,
        flags=re.MULTILINE,
    )
    assert match is not None, "scanner CODE_EXTENSIONS assignment is missing"
    return tuple(f".{extension}" for extension in match.group(1).split(","))


# Anchor on markers, not on prose. The previous anchors were sentences from the
# README body, and a README rewrite deleted them along with the extension list
# they bracketed — the contract broke because the text it quoted was editable.
SCANNER_EXTENSIONS_START = "<!-- README-CONTRACT:SCANNER-EXTENSIONS:START -->"
SCANNER_EXTENSIONS_END = "<!-- README-CONTRACT:SCANNER-EXTENSIONS:END -->"


def documented_extensions(text: str, start: str, end: str) -> tuple[str, ...]:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return tuple(re.findall(r"`(\.[a-z]+)`", text[start_index:end_index]))


def main() -> None:
    security = normalized(SECURITY)
    skill = normalized(SKILL)
    pattern_reference = normalized(PATTERN_REFERENCE)
    grep_patterns = normalized(GREP_PATTERNS)
    applying_fixes = normalized(APPLYING_FIXES)
    scanner_source = SCANNER.read_text(encoding="utf-8")
    scanner = " ".join(scanner_source.split())
    verification_rules = normalized(VERIFICATION_RULES)
    readme = README.read_text(encoding="utf-8")
    evals = json.loads(EVALS.read_text(encoding="utf-8"))["evals"]
    eval_28 = next(case for case in evals if case["id"] == 28)
    eval_29 = next(case for case in evals if case["id"] == 29)
    eval_30 = next(case for case in evals if case["id"] == 30)
    eval_34 = next(case for case in evals if case["id"] == 34)
    eval_35 = next(case for case in evals if case["id"] == 35)
    eval_36 = next(case for case in evals if case["id"] == 36)
    eval_28_text = " ".join(
        [eval_28["expected_output"], *eval_28["assertions"]]
    )
    eval_29_text = " ".join(
        [eval_29["expected_output"], *eval_29["assertions"]]
    )
    eval_30_text = " ".join(
        [eval_30["expected_output"], *eval_30["assertions"]]
    )
    eval_34_text = " ".join(
        [eval_34["expected_output"], *eval_34["assertions"]]
    )
    eval_35_text = " ".join(
        [eval_35["expected_output"], *eval_35["assertions"]]
    )
    eval_36_text = " ".join(
        [eval_36["expected_output"], *eval_36["assertions"]]
    )

    pattern_reference_substring_fix = (
        "`expect(page.url()).toContain(x)` → "
        "`await expect.poll(() => page.url()).toContain(x)`"
    )
    applying_fixes_substring_fix = (
        "`expect(page.url()).toContain(x)` (substring) | "
        "`await expect.poll(() => page.url()).toContain(x)`"
    )
    assert pattern_reference_substring_fix in pattern_reference
    assert applying_fixes_substring_fix in applying_fixes
    assert (
        "`expect(page.url()).toContain(x)` → "
        "`await expect(page).toHaveURL(x)`"
    ) not in pattern_reference
    count_fix = (
        "| `#4c-4e` `expect(await x.count()).toBe(N)` | "
        "`await expect(x).toHaveCount(N)` |"
    )
    assert count_fix in applying_fixes
    assert (
        "| `#4c-4e` / `#15` `expect(await x.count()).toBe(N)` |"
    ) not in applying_fixes
    all_fix = (
        "| `#4c-4e` `expect(await x.all()).toHaveLength(N)` | "
        "`await expect(x).toHaveCount(N)` |"
    )
    assert all_fix in applying_fixes
    assert (
        "| `#15` `expect(await x.all()).toHaveLength(N)` |"
    ) not in applying_fixes
    assert (
        "| `#15` `expect(locator).toBeVisible()` (no await) | "
        "`await expect(locator).toBeVisible()` |"
    ) in applying_fixes

    assert "scanner findings remain scoped to that requested root" in security
    assert (
        "Provenance resolution may read relative fixture/support modules "
        "elsewhere within the containing project"
    ) in security

    conditional_boundary = (
        "load-bearing promised-outcome assertion"
    )
    assert conditional_boundary in skill
    assert (
        "independent unconditional meaningful postcondition or "
        "failure-producing action"
    ) in skill
    assert conditional_boundary in eval_28_text
    assert "independent unconditional meaningful postcondition" in eval_28_text
    assert "failure-producing action" in eval_28_text
    assert "optional secondary check" in eval_28_text

    assert "Storybook interaction tests are out of scope" in applying_fixes
    assert "Playwright and Cypress only" in applying_fixes
    assert "treated as in-scope component E2E" not in applying_fixes

    suppression_contract = (
        "Treat `// JUSTIFIED:` as a request to suppress a documented "
        "exception, not as proof that every marked hit is safe."
    )
    p0_candidate_contract = (
        "For P0, keep the hit visible as a deduplicated "
        "`[P0?][JUSTIFIED-REVIEW]` candidate until Phase 2 or an external "
        "verifier confirms the rationale; it still gates "
        "`E2E_SMELL_FAIL_ON=p0-candidate` before that confirmation."
    )
    for surface in (skill, grep_patterns):
        assert suppression_contract in surface
        assert p0_candidate_contract in surface
        assert "Focused Test Leak is never suppressible" in surface
        assert "a hit is intentional and must be **skipped**" not in surface

    assert (
        "one deliberately narrow **position 2** shape: a marker immediately "
        "above a brace-delimited `page.evaluate()` or `page.waitForFunction()` "
        "callback"
    ) in skill
    assert "within the scanner's bounded 24-line lexical window" in skill
    assert "`\\btoBeAttached\\b` name candidate" in grep_patterns
    assert "drops quoted/comment-only names" in grep_patterns
    assert "bounded 24-line/500-character whitespace gap" in grep_patterns
    assert "excludes `.not` chains across whitespace/comments/lines" in grep_patterns
    assert "finite lexical scan, not unbounded parser semantics" in grep_patterns
    assert "e2e,triage,positive-attached" in scanner
    assert (
        "distinct fresh-context, read-only e2e-reviewer actor/process that did "
        "not write, debug, or repair the candidate"
    ) in verification_rules
    assert "otherwise V6 cannot be `PASS`" in verification_rules

    assert "Raw DOM query confirmation" in skill
    for allowed_shape in (
        "computed style",
        "child counts",
        "cross-element relationships",
    ):
        assert allowed_shape in skill
    for guard in ("computed-style", "child-count", "cross-element"):
        assert guard in eval_29_text
    assert "exactly one final #6 finding" in eval_29_text
    absence_wording = (
        "assertion that can pass without proving the locator ever matched"
    )
    assert absence_wording in pattern_reference
    assert absence_wording in " ".join(
        assertion
        for case in evals
        for assertion in case["assertions"]
    )
    assert "Report it as an assertion that cannot fail" not in pattern_reference
    assert (
        "run_check P1 '#6' 'Raw DOM query inside test code' "
        "'document\\.(querySelector(?:All)?|getElementById)' "
        '"$ALL_CODE_GLOB" \'e2e,triage,executable-line\''
    ) in scanner

    expected_extensions = scanner_extensions(scanner_source)
    assert expected_extensions == (
        ".ts",
        ".js",
        ".tsx",
        ".jsx",
        ".mts",
        ".mjs",
        ".cts",
        ".cjs",
    )
    phase_zero_extensions = documented_extensions(
        SKILL.read_text(encoding="utf-8"),
        "extension set:",
        "Inspect **actual import statements**",
    )
    readme_extensions = documented_extensions(
        readme,
        SCANNER_EXTENSIONS_START,
        SCANNER_EXTENSIONS_END,
    )
    assert phase_zero_extensions == expected_extensions
    assert readme_extensions == expected_extensions

    for contract in (
        "classify those sampled files only",
        "never excludes the containing directory or candidate root",
        "run the Phase 1 scanner across the full candidate root",
        "trace relative imports and re-exports",
        "transitive Playwright/Cypress provenance in scope",
    ):
        require_contract(skill, contract, "SKILL.md")
        assert contract in eval_30_text
    phase_zero_eval_files = [
        "evals/files/phase0-transitive-unit.spec.ts",
        "evals/files/phase0-transitive-review.spec.ts",
        "evals/files/phase0-transitive-barrel.ts",
        "evals/files/phase0-transitive-support.ts",
        "evals/files/phase0-transitive-fixture.ts",
    ]
    assert eval_30["prompt"] == (
        "Review the candidate test root in evals/files/phase0-transitive-*. "
        "Determine framework scope and report the findings."
    )
    assert eval_30["files"] == phase_zero_eval_files
    phase_zero_fixture_dir = EVALS.parent / "files"
    phase_zero_fixture_bytes = {
        path.name: path.read_bytes()
        for path in (
            phase_zero_fixture_dir / "phase0-transitive-unit.spec.ts",
            phase_zero_fixture_dir / "phase0-transitive-review.spec.ts",
            phase_zero_fixture_dir / "phase0-transitive-barrel.ts",
            phase_zero_fixture_dir / "phase0-transitive-support.ts",
            phase_zero_fixture_dir / "phase0-transitive-fixture.ts",
        )
    }
    assert phase_zero_fixture_bytes["phase0-transitive-unit.spec.ts"] == (
        b"import { describe, expect, it } from '@jest/globals';\n"
        b"\n"
        b"describe('formatter', () => {\n"
        b"  it('formats a label', () => {\n"
        b"    expect('ready'.toUpperCase()).toBe('READY');\n"
        b"  });\n"
        b"});\n"
    )
    assert phase_zero_fixture_bytes["phase0-transitive-review.spec.ts"] == (
        b"import { expect, test } from './phase0-transitive-barrel';\n"
        b"\n"
        b"test.only('shows the saved state', async ({ page }) => {\n"
        b"  await page.goto('/settings');\n"
        b"  await expect(page.getByText('Saved')).toBeVisible();\n"
        b"});\n"
    )
    assert phase_zero_fixture_bytes["phase0-transitive-barrel.ts"] == (
        b"export { expect, test } from './phase0-transitive-support';\n"
    )
    assert phase_zero_fixture_bytes["phase0-transitive-support.ts"] == (
        b"export { expect, test } from './phase0-transitive-fixture';\n"
    )
    assert phase_zero_fixture_bytes["phase0-transitive-fixture.ts"] == (
        b"import { expect, test as base } from '@playwright/test';\n"
        b"\n"
        b"export const test = base.extend({});\n"
        b"export { expect };\n"
    )
    review_lines = phase_zero_fixture_bytes[
        "phase0-transitive-review.spec.ts"
    ].splitlines()
    assert review_lines[2].startswith(b"test.only(")
    assert sum(line.startswith(b"test.only(") for line in review_lines) == 1
    assert "test.only" in eval_30_text
    assert "#7" in eval_30_text

    positional_pom_contract = (
        "POM encapsulation is not an exemption: moving a positional locator "
        "into a semantically named Page Object method does not make it stable."
    )
    positional_scope_contract = (
        "Scan Playwright/Cypress-proven POM/support files as well as specs for "
        "positional locators."
    )
    positional_name_contract = (
        "Only a method name that explicitly promises positional access may "
        "use the method-name exemption."
    )
    responsive_position_contract = (
        "When a positional locator targets a collection that is conditionally "
        "rendered or reordered by viewport, feature flags, permissions, or "
        "state, inspect those render conditions before resolving the candidate."
    )
    for surface in (skill, pattern_reference, grep_patterns):
        assert positional_scope_contract in surface
        assert positional_pom_contract in surface
        assert positional_name_contract in surface
        assert responsive_position_contract in surface
    for contract in (
        "POM encapsulation is not an exemption",
        "semantically named helper",
        "1024px viewport",
        "getCellByIndex",
        "explicitly promises positional access",
    ):
        assert contract in eval_34_text
    assert eval_34["files"] == [
        "evals/files/positional-pom/admin-rooms.ts",
        "evals/files/positional-pom/responsive-rooms-table.tsx",
    ]
    positional_fixture_dir = EVALS.parent / "files" / "positional-pom"
    positional_pom = (
        positional_fixture_dir / "admin-rooms.ts"
    ).read_text(encoding="utf-8")
    responsive_table = (
        positional_fixture_dir / "responsive-rooms-table.tsx"
    ).read_text(encoding="utf-8")
    assert (
        "getRoomMessagesCountCell(name: string): Locator" in positional_pom
    )
    assert "getByRole('cell').nth(3)" in positional_pom
    assert "getCellByIndex(name: string, index: number)" in positional_pom
    assert "getByRole('cell').nth(index)" in positional_pom
    assert "useMediaQuery('(min-width: 1024px)')" in responsive_table
    assert "<td>{type}</td>" in responsive_table
    assert "showDetails && <td>{messages}</td>" in responsive_table
    assert (
        f"admin-rooms.ts line {source_line_number(positional_pom, 'nth(3)')} "
        "as #10a P1"
    ) in eval_34_text
    assert (
        "Does NOT report admin-rooms.ts line "
        f"{source_line_number(positional_pom, 'nth(index)')} "
        "as #10a"
    ) in eval_34_text
    responsive_condition_line = source_line_number(
        responsive_table, "useMediaQuery('(min-width: 1024px)')"
    )
    responsive_messages_line = source_line_number(
        responsive_table, "showDetails && <td>{messages}</td>"
    )
    assert (
        "responsive-rooms-table.tsx line "
        f"{responsive_condition_line} and line {responsive_messages_line}"
    ) in eval_34_text

    diff_review_fixture_dir = EVALS.parent / "files" / "diff-review"
    diff_review_fixture_bytes = {
        path.name: path.read_bytes()
        for path in (
            diff_review_fixture_dir / "README.md",
            diff_review_fixture_dir / "changed-orders.spec.ts",
            diff_review_fixture_dir / "orders-page.ts",
            diff_review_fixture_dir / "legacy.spec.ts",
            diff_review_fixture_dir / "profile-panel.tsx",
        )
    }
    assert diff_review_fixture_bytes["README.md"] == (
        b"Never use positional nth selectors in Playwright locators. "
        b"Prefer role, label,\n"
        b"test id, or text locators that describe the user-visible target.\n"
    )
    assert diff_review_fixture_bytes["changed-orders.spec.ts"] == (
        b"import { expect, test } from '@playwright/test';\n"
        b"import { OrdersPage } from './orders-page';\n"
        b"\n"
        b"test('exports a paid order', async ({ page }) => {\n"
        b"  const orders = new OrdersPage(page);\n"
        b"\n"
        b"  await orders.goto();\n"
        b"  await orders.exportPaidOrder();\n"
        b"  await expect(page.getByRole('status')).toHaveText('Export started');\n"
        b"});\n"
    )
    assert diff_review_fixture_bytes["orders-page.ts"] == (
        b"import type { Locator, Page } from '@playwright/test';\n"
        b"\n"
        b"export class OrdersPage {\n"
        b"  constructor(private readonly page: Page) {}\n"
        b"\n"
        b"  async goto(): Promise<void> {\n"
        b"    await this.page.goto('/orders');\n"
        b"  }\n"
        b"\n"
        b"  paidOrderExportButton(): Locator {\n"
        b"    return this.page.getByRole('row', { name: /paid/i }).nth(2).getByRole('button', {\n"
        b"      name: 'Export',\n"
        b"    });\n"
        b"  }\n"
        b"\n"
        b"  async exportPaidOrder(): Promise<void> {\n"
        b"    await this.paidOrderExportButton().click();\n"
        b"  }\n"
        b"}\n"
    )
    assert diff_review_fixture_bytes["legacy.spec.ts"] == (
        b"import { expect, test } from '@playwright/test';\n"
        b"\n"
        b"test.only('legacy smoke still opens dashboard', async ({ page }) => {\n"
        b"  await page.goto('/dashboard');\n"
        b"  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();\n"
        b"});\n"
    )
    assert diff_review_fixture_bytes["profile-panel.tsx"] == (
        b"export function ProfilePanel({ name }: { name: string }) {\n"
        b"  return (\n"
        b"    <section aria-label=\"Profile\">\n"
        b"      <h2>{name}</h2>\n"
        b"      <button type=\"button\">Edit profile</button>\n"
        b"    </section>\n"
        b"  );\n"
        b"}\n"
    )
    orders_page = diff_review_fixture_bytes["orders-page.ts"].decode()
    legacy_spec = diff_review_fixture_bytes["legacy.spec.ts"].decode()
    assert source_line_number(orders_page, "nth(2)") == 11
    assert source_line_number(legacy_spec, "test.only") == 3
    assert eval_35["files"] == [
        "evals/files/diff-review/changed-orders.spec.ts",
        "evals/files/diff-review/orders-page.ts",
        "evals/files/diff-review/legacy.spec.ts",
        "evals/files/diff-review/README.md",
    ]
    assert eval_36["files"] == [
        "evals/files/diff-review/profile-panel.tsx",
    ]
    for contract in (
        "diff mode",
        "nearest README.md",
        "Run Phase 1 with the bundled scanner once per changed in-scope E2E source artifact before Phase 2",
        "never pass multiple changed-file paths to one scanner invocation",
        "scan.sh accepts at most one root and fails closed on multiple roots",
        "Do not run Phase 1 against unchanged context-only files",
        "obvious smell encountered while reading supplied unchanged context may be advisory, but not a Phase 1 scan target or blocker",
        "introduced #10a P1",
        "Attribution (diff mode)",
        "pre-existing/advisory",
        "worsened attribution",
        "changed hunk in Playwright/Cypress specs, POMs, support files, fixtures, custom commands, or E2E config artifacts",
        "unchanged E2E line newly unreliable",
        "causal diff evidence",
        "not count it as a PR blocker or top priority",
        "unchanged context-only files",
        "Review Scope and Evidence",
        "Mode",
        "Behavior under review",
        "Diff base/range",
        "Changed E2E artifacts",
        "Context-only files consulted",
        "Static evidence",
        "Runtime evidence",
        "Independent verification",
        "Limitations/exclusions",
        "scanner tier coverage and semantic checks",
        "Runtime evidence refers only to target-controlled project runtime",
        "must not count the bundled scanner as runtime",
        "none, unavailable, or not executed",
    ):
        assert contract in eval_35_text
    for contract in (
        "no in-scope E2E diff",
        "does not change any Playwright/Cypress spec, POM, support file, fixture, custom command, or E2E config artifact",
        "do not perform a general app review",
        "Review Scope and Evidence",
    ):
        assert contract in eval_36_text
    for contract in (
        "Review Scope and Evidence",
        "diff mode",
        "Every field is mandatory",
        "`Static evidence` records scanner tier coverage and semantic checks",
        "`Runtime evidence` means target-controlled project runtime, never the bundled scanner",
        "use `none`, `unavailable`, or `not executed`",
        "Every diff finding must include the explicit `Attribution (diff mode)` field",
        "Unchanged files are context-only evidence",
        "Phase 1 remains mandatory in diff mode",
        "run the bundled scanner against each changed in-scope E2E source artifact",
        "Invoke `scan.sh` once per artifact",
        "it accepts at most one scan root and fails closed on multiple roots",
        "Never pass a changed-file list as multiple arguments to one scanner invocation",
        "Phase 1 must not scan unchanged context-only files",
        "scanner findings are limited to changed in-scope source artifacts",
        "An obvious smell encountered while reading supplied unchanged context may be advisory, but not a Phase 1 scan target or blocker",
        "`introduced`: the diff adds the issue to a changed in-scope E2E artifact",
        "`worsened`: a changed in-scope E2E hunk makes an unchanged E2E line newly unreliable; cite the causal diff evidence",
        "`pre-existing`: present at base and not worsened; advisory only",
        "omit the candidate from blockers, Review Summary totals, and top priorities",
        "outputs include only introduced or causally worsened findings",
        "consult the nearest README.md before resolving selector-stability findings",
        "Project conventions may only add a finding or raise confidence in one",
        "never downgrades severity, suppresses a finding, or narrows review scope",
        "conflicting with local convention",
        "when runtime was not executed, say so and recommend the relevant E2E run",
        "If a PR changes no in-scope E2E artifact, return `no in-scope E2E diff`",
        "do not perform a general app review",
    ):
        require_contract(skill, contract, "SKILL.md")

    for contract in (
        "require both Python 3 and `rg` with PCRE2 support",
        "NUL-safe candidate identity records",
        "separate from optional Tier 2 AST tooling",
    ):
        require_contract(skill, contract, "SKILL.md")
    for contract in (
        "PCRE2-capable `rg` and Python 3",
        "NUL-safe candidate identity records",
        "separate from optional Tier 2 AST tooling",
    ):
        require_contract(" ".join(readme.split()), contract, "README.md")

    for path in TRANSLATED_READMES:
        translated = path.read_text(encoding="utf-8")
        assert (
            documented_extensions(
                translated, SCANNER_EXTENSIONS_START, SCANNER_EXTENSIONS_END
            )
            == expected_extensions
        )
        for prerequisite in ("PCRE2", "Python 3", "NUL-safe", "Tier 2 AST"):
            assert prerequisite in translated

    print("reviewer documentation contracts: pass")


if __name__ == "__main__":
    main()

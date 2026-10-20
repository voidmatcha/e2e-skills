# Phases 2.5 and 3, and Review Output

Read this file after findings are verified and before synthesizing systemic issues, coverage gaps, or the final review. It contains the full systemic/coverage procedure and every output template and discipline rule; `SKILL.md` retains their non-negotiable outcomes.

**Contents:** Phase 2.5: Systemic Issues · Phase 3: Coverage Gap Analysis (After Review) · Output Format · Output discipline

## Phase 2.5: Systemic Issues

After individual findings are catalogued, synthesize cross-cutting patterns that affect the test suite as a whole. Check for:

| Issue | How to check | Sev |
|-------|-------------|-----|
| **No authentication strategy** (suite-level rollup of #12) | 3+ confirmed #12 P0 cases across the suite pass against a login/wrong surface because auth is absent. Always emit a single rollup line here; do not enumerate per-file findings — those belong in Phase 2. | P0 |
| **No stable user-facing selectors** | [Playwright] Zero uses of `getByRole` / `getByTestId` / `getByLabel` / `getByPlaceholder` / `getByText` across all files. [Cypress] Zero uses of `[data-cy=]` / `[data-testid=]` selectors and no `cy.findBy*` calls (cypress-testing-library). | P2 |
| **Missing `beforeEach`** | 3+ tests in a `describe` repeat the same setup code (POM instantiation + navigation) | P2 |

**Deduplication rule:** Phase 2.5 issues are *suite-wide* findings. If an issue is already raised once per file in Phase 2 (e.g. #12 Missing Auth Setup), do not also list each file under Phase 2.5 — emit a single rollup line with the affected file count.

Output as a dedicated section:
```markdown
## Systemic Issues
- **No authentication strategy:** N tests pass against a login/wrong surface because auth setup is absent. Add `storageState` or an auth fixture. (Rolls up confirmed #12 P0 cases across N files.)
- **No stable user-facing selectors:** [Playwright] 0 uses of getByRole/getByTestId across N files. [Cypress] 0 uses of `[data-cy=]`/`[data-testid=]` across N files. Migrate to user-facing locators.
```

Only report systemic issues that are actually present. Skip this section if none apply.

---

## Phase 3: Coverage Gap Analysis (After Review)

After completing Phase 1 + 2 + 2.5, identify scenarios the test suite does NOT cover. Scan the page/feature under test and flag missing:

| Gap Type | What to look for |
|----------|-----------------|
| Error paths | Form validation errors, API failure states (4xx/5xx), network offline, timeout retry, partial-success batches |
| Edge cases | Empty state, max-length input, special characters, zero-result lists, very-long content (overflow/truncation) |
| Race / concurrent | Optimistic-update rollback, double-click submit, in-flight request when user navigates away, stale-while-revalidate display |
| Accessibility | Keyboard navigation order, screen reader labels (`aria-label`/`aria-describedby`), focus management after modal close, focus trap on dialog |
| Auth boundaries | Unauthorized redirect (`/login?from=...`), expired session mid-action, role-based UI visibility, multi-tenant scope leak |
| Responsive / device | Mobile viewport (< 768px), touch vs hover interactions, locale-dependent formatting (date/currency/RTL) |

**Context-aware suggestions are mandatory.** Each gap must reference a SPECIFIC finding from Phase 1/2 — pattern ID (`#4a`), file:line, or assertion target. Generic suggestions ("add error path tests") that could apply to any test suite are LOW value and should be omitted. If you can't tie a gap to an observed pattern, don't list it.

**Triage rule**: gaps that "interact with" a P0 finding are highest value. Example: a #5a conditional bypass observed in profile.spec.ts → suggest a coverage gap test for the OPPOSITE branch (the one the `if` skipped) — that branch was the unintentional silent-pass surface.

**Output:** List up to 5 highest-value missing scenarios as suggestions, not requirements. Format:

```markdown
## Coverage Gaps (Suggestions)
1. **[Edge case]** No test for empty dashboard state — currently `toBeGreaterThanOrEqual(0)` masks this (see #4a-1). Verify empty-state message when no metrics exist.
2. **[Error path]** No test for form submission with server error — the profile update test (settings:9) has no error path at all.
3. **[Race]** `if (await spinner.isVisible())` at checkout.spec.ts:42 (see #5a above) skips the slow-network branch entirely — add a route-throttled variant that forces the spinner path.
```

---

## Output Format

Start every review with this evidence header:

```markdown
## Review Scope and Evidence
- **Mode:** [full mode | diff mode]
- **Behavior under review:** [suite/root behavior or PR/diff behavior]
- **Diff base/range:** [base...head, patch source, changed-file list, or N/A]
- **Changed E2E artifacts:** [changed Playwright/Cypress specs, POMs, support, fixtures, custom commands, and E2E config artifacts; or none]
- **Context-only files consulted:** [unchanged imports/POMs/fixtures/support/app files read as evidence]
- **Static evidence:** [scanner tier coverage and semantic checks, or none]
- **Runtime evidence:** [command/result, or "not executed"; state when runtime was not executed and recommend the relevant E2E run]
- **Independent verification:** [V1-V6 evidence or recommended/unexecuted]
- **Limitations/exclusions:** [out-of-scope files, missing base, skipped runtime, or none]
```

Every field is mandatory; use `none`, `unavailable`, or `not executed`. `Static evidence` records scanner tier coverage and semantic checks. `Runtime evidence` means target-controlled project runtime, never the bundled scanner. In diff mode, identify context-only files; when runtime was not executed, say so and recommend the relevant E2E run. Emit the section even for `no in-scope E2E diff`.

For an executed portable probe, include its mode, frozen plan/digest, exact native selector, normal/changed/restored results, linked failure or observer artifacts, phase app provenance, approved commands/environment, original-input checks, and retained workspace paths in `Runtime evidence`. V2 `ASSERTION_SENSITIVE` proves assertion sensitivity only; it is not V3 `DETECTED`. Leave unmeasured V1–V6 rules explicitly unverified. Missing prepared runner or evidence means `recommended/unexecuted` or `CANNOT_VERIFY`, not a fabricated result.

For an executed V3 adapter check, include its adapter ID, sourced behavior promise, exact test selector, normal/fault/restored phase results, independent observer evidence, approved commands/environment, retained output path, and `DETECTED` / `SURVIVED` / `CANNOT_VERIFY` in `Runtime evidence`. Report missing promise, adapter, or approval as `recommended/unexecuted`; do not manufacture a runtime result. `SURVIVED` alone never creates a catalog finding or changes severity. A valid `DETECTED` result proves only the exercised fault. Keep inconclusive runs and non-catalog observations in the evidence header rather than inventing a finding.

Present findings grouped by severity:

```markdown
## [P0/P1/P2] [filename] — #[pattern ID] [issue type]

### `[test name or POM method]`
- **Issue:** [description]
- **Attribution (diff mode):** [introduced | worsened | pre-existing | N/A in full mode]
- **Fix:** [name change / assertion addition / merge / deletion]
- **Verification:** [smallest applicable V1–V6 proof from `references/verification-rules.md`, or `N/A`; state `recommended` unless an actual command/result proves it ran]
- **§4.1 row:** [REQUIRED whenever **Code:** is present — quote the AVOID → USE row for this pattern verbatim from `references/fix-replacements.md` or `references/applying-fixes.md` §4.1 (or its conditional `references/rtl-jest-dom-fixes.md` row for RTL #4f), or write `no row (judgement call)` if the table has none]
- **Code:**
  ```typescript
  // concrete code to add or change
  ```
```

Every finding heading names its pattern ID from the Quick Reference, such as `## [P0] tests/login.spec.ts — #5a Conditional assertion bypass`; a heading with only a prose title cannot be matched to the catalog by readers or tools. When one block reports several patterns, list every ID, such as `#9 #10a`.
Every finding heading is a level-2 heading starting at the beginning of its line with `## [`, exactly as the template shows; never nest it under another heading such as `## Findings` or use `### [P`. Test-case subheadings inside a finding remain `###`.

Every diff finding must include the explicit `Attribution (diff mode)` field; attribution only in a heading is insufficient.

Cite every location as a full `path:line` relative to the repository root, such as `apps/web/playwright/login.e2e.ts:42`. Do not cite absolute paths, which expose the reviewer's local directories when a review is shared, or shortened suffixes such as `tasks/login.ts:42`, which can match more than one file.

The **§4.1 row** field is a slot, not a reminder: it cannot be filled without opening `references/fix-replacements.md` or `references/applying-fixes.md` (or its conditional `references/rtl-jest-dom-fixes.md` row for RTL #4f), which is the point. A fix emitted with that field blank or paraphrased was written without the canonical replacement table and must be redone against it.

**After all findings, append a summary table and top priorities:**

```markdown
## Review Summary

| Sev | Count | Top Issue | Affected Files |
|-----|-------|-----------|----------------|
| P0  | 3     | Missing Then | auth.spec.ts, form.spec.ts |
| P1  | 5     | Flaky Selectors | settings.spec.ts |
| P2  | 2     | Unused POM Members | settings-page.ts |

**Total: 10 issues across 4 files.**

### Top 3 Priorities
1. **Remove `test.only`** in auth.spec.ts — CI is running only 1 of 6 tests
2. **Remove try/catch** around assertion in settings.spec.ts — test can never fail
3. **Add assertions** to 4 tests with zero verification (redirect, export, toggle, notification)
```

The "Top N Priorities" section should list the 3-5 highest-impact fixes in concrete, actionable terms. This helps developers know where to start without scanning all P0 findings.

### Output discipline

These constrain what the review says, not what it detects. They never change a pattern's ID, severity, or framework scope, and none of them is satisfied by reporting less than the catalog requires.

- **Clean result:** report that no catalog findings were confirmed, and carry the evidence header's scope and limitation fields unchanged. Emit no findings rows, no `Coverage Gaps` list, and no selector, payload, coverage, style, or general-improvement advice — Phase 3 requires every gap to cite a confirmed Phase 1/2 finding, so a clean result has nothing to cite.
- **Positive result:** report only confirmed catalog findings. Keep limitations in the `Limitations/exclusions` header field, never inside a finding or the summary. Do not relabel speculative advice as a non-blocking observation, nit, or optional improvement to get it past this rule: if it is not a confirmed catalog finding, it does not ship.
- **One fix per finding:** give the single minimal evidence-backed fix. Add a second only when the pattern contract genuinely requires coordinated changes across files, and then say which change forces the other.
- **No weakening alternatives:** never offer an alternative that reduces what the test proves — relaxing a matcher, widening a timeout, deleting the assertion instead of proving the locator, or adding `force: true` to get past an actionability failure.
- **Calibrated causal language:** write `always` only when the evidence proves an unconditional outcome (a locator that matches nothing under `toHaveCount(0)` does always pass). Otherwise write `can`, `may`, or `when <condition>`.

**Final follow-up:** Before ending, check SKILL.md § Optional portable V2/V3 probes. If you recommend a useful, unexecuted V2/V3 probe, append one question **after** the review and priorities: name the test, mode, bounded benefit, and additional token/execution-time cost. A `Verification: recommended` bullet alone does not satisfy this step. State that execution has not occurred. Omit the question for explicit static-only requests, no meaningful candidate, or runtime work already authorized; proceed with existing authorization instead. This scoped offer is permitted by output discipline and is not another finding.

**Severity classification:**
- **P0 (Must fix):** Test silently passes when the feature is broken — no real verification happening. Both halves are required. Passing while the feature is broken is not enough on its own: if the test really verifies something it promised, and only a second promised effect goes unchecked, that is P1. `#22` sits there — the optimistic UI assertion does verify client behavior, and the unverified part is the write. A pattern's severity is its usual case; an instance can be reported higher when it meets the P0 definition outright, the way `#12` already conditions P0 on the wrong surface actually satisfying the test's assertions.
- **P1 (Should fix):** Test works but gives poor diagnostics, wastes CI time, or misleads developers
- **P2 (Nice to fix):** Weak but not wrong — maintenance and robustness improvements

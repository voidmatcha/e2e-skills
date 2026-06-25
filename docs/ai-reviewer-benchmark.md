# Benchmark: e2e-reviewer vs lint vs AI PR reviewers

How does `e2e-reviewer` actually compare to the tools a team already has — the standard
ESLint plugins and the AI PR reviewers (CodeRabbit, Copilot, Codex, Sourcery, Gemini,
Cursor, Ellipsis, Greptile)? This page reports a real, reproducible head-to-head on
**100 open-source pull requests** that an AI reviewer had already reviewed, scoped to one
question: **which tool catches E2E tests that pass while the feature is broken (silent
always-pass), without crying wolf?**

It is deliberately honest, including where we lose and three limitations that cut against
us. The scripts are in the repo so you can re-run it.

## TL;DR

- Corpus: **100 PRs across 77 distinct repositories**, each one already reviewed by one of
  8 AI PR reviewers, each modifying Playwright or Cypress spec files.
- A neutral LLM judge read every spec file, established the ground-truth set of genuine
  E2E test-trust issues (110 across the corpus), then scored each tool against it.

| Tool | Recall (real issues caught) | False positives / noise | Caught what the other two missed |
|------|------------------------------|--------------------------|----------------------------------|
| **e2e-reviewer (LLM Phase 2)** | **78 / 110 (71%)** | **0** | **47** |
| lint (eslint-plugin-playwright / -cypress) | 45 / 110 (41%) | 0 | — |
| AI PR reviewer (inline spec comments) | 10 / 110 (9%) | 72 | 4 |

Per-case winner, on the 33 PRs that contained a real issue (67 PRs had none):
**e2e-reviewer 19, lint-sufficient 11, AI reviewer 2, tie 1.**

The headline: on the narrow target of **E2E test trustworthiness**, the verification layer
had the best recall and perfect precision, and uniquely caught 47 real silent-always-pass
issues that both lint and the AI reviewer missed. It is **not** that the AI reviewers are
weak (see Limitations) — it is that a curated, E2E-specialised checker beats a general
reviewer's split attention on this one axis.

## What the mechanical layer alone shows

Before the LLM layer, the purely mechanical detectors over the same 100 PRs:

| Detector | PRs with >=1 finding |
|----------|----------------------|
| lint (eslint-plugin-playwright / -cypress) | 75 |
| our scanner (`scan.sh`, regex + ast-grep tiers) | 55 |
| AI reviewer inline spec comments | 39 |

Our **scanner adds net-new mechanical coverage over lint in only 8 of 100 PRs** — and the
AI reviewers surfaced spec issues our scanner missed in 21. The mechanical scanner is a
candidate generator, not the product; on its own it is largely subsumed by lint. The
differentiation is entirely in the LLM Phase-2 verification layer, which is what the
scoreboard above measures.

## Examples of what only e2e-reviewer caught

- A wall of `expect(locator).toBeTruthy()` / `.not.toBeNull()` on Playwright Locators
  (always truthy, never null) as the sole assertion of 17 tests in one suite.
- `expect(await locator).toBeVisible()` repeated 9 times — awaiting a Locator returns the
  Locator, so the construct never asserts.
- Tautological assertions: `toBeGreaterThanOrEqual(0)` on a count, `toHaveTitle(/.*/)`,
  `expect([200, 401, 403]).toContain(status)` accepting a broken endpoint as a pass.
- A delete test that clicks Delete and never asserts the entity is gone (pattern #2).
- A "terms of use accepted" test asserting only the pre-state, never the post-accept state.

## Where we lost or tied (honest)

- **lint-sufficient (11 PRs):** the only real issue was a `waitForTimeout` flake or a
  missing-`await`/`expect-expect` shape that `eslint-plugin-playwright` already flags. Lint
  is a strong, cheap baseline — run it first.
- **AI reviewer won (2 PRs):** the spec was clean and the only real issue was outside our
  silent-always-pass taxonomy; the general reviewer's broader lens caught it and we did not.

## Limitations (these cut against the result — read them)

1. **The AI-reviewer number is under-measured.** We counted only the bot's **inline
   spec-file comments**, capped at 6 per PR, and the bots review the *entire* PR (all files,
   all concerns) with split attention — not E2E test trust specifically. So "AI reviewer
   caught 10" means "their inline spec comments addressed 10 of our ground-truth issues,"
   **not** "CodeRabbit/Copilot/etc. are weak." Much of their 72 "noise" is genuine
   DRY/typo/correctness feedback that is simply off-target for *this* ground truth.
2. **Judge/reviewer model affinity.** Our Phase-2 reviewer and the neutral judge are the
   same model family, which can inflate our recall and deflate our false-positive count.
   A human-judged or cross-model-judged run would be stronger evidence. *Update:* the
   contestable unique catches (the 15 cases where ours beat both lint and the AI reviewer;
   there are no false positives to contest) were re-judged by an independent cross-model
   judge, OpenAI gpt-5.5 via Codex. It agreed on 13/15 (87%); the two disagreements were
   reasoned definitional edges, not overturned defects. The headline holds directionally
   under a different model family rather than collapsing.
3. **LLM-set ground truth, single sample.** The 110 "real issues" were established by an LLM
   judge reading each file, not by a human panel, over one 100-PR snapshot. Treat the exact
   numbers as indicative, not definitive.

## What we changed as a result

The benchmark fed directly back into the ruleset, and the lesson was mostly *what not to
add*:

- Candidate mechanical rules mined from bot comments (custom-sleep helper, external-URL
  navigation, hardcoded-localhost-URL) were **rejected** after measuring prevalence across
  77 repos: near-zero or ~100% false-positive once config context is considered. A bot
  comment is a candidate, not a general rule.
- The one real, cross-repo signal — *delete/remove tests that never verify removal* — is
  already pattern **#2 (Missing Then)**, an LLM-only (Phase 2) check. The benchmark's FP
  analysis was folded into #2 as explicit accept-criteria (do not flag API-delete+404,
  cleanup/teardown, success-toast confirmations, helper-embedded assertions, or
  non-entity "remove"). See `skills/e2e-reviewer/references/pattern-reference.md`.

## Reproduce

The full per-case results — every PR, the neutral judge's verdict and rationale, and which
tool caught what — are committed as evidence in
[`ai-reviewer-100-results.json`](benchmarks/ai-reviewer-100-results.json), so the aggregate
numbers above can be independently re-derived. The method, reproducible end to end:

1. Find PRs an AI reviewer commented on that touch Playwright/Cypress specs
   (GitHub search: `is:pr commenter:<bot> playwright`).
2. Download the changed spec files at the PR head SHA (no full clone).
3. Run, per PR: `eslint` with `eslint-plugin-playwright`/`-cypress`; `scan.sh`; and collect
   the bot's inline spec comments.
4. For each material PR, run the `e2e-reviewer` Phase-2 review and a neutral judge that
   establishes ground truth and scores all three tools.

No third-party repositories are modified; all analysis is read-only.

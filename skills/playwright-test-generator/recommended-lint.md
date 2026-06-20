# Recommended lint hardening (propose by default)

When generating a new E2E suite (or generating into a project that has no E2E lint
config), **propose** this hardening so the generated tests cannot silently regress into
the anti-patterns `e2e-reviewer` exists to catch. This is the prevention layer.

Propose, do not impose. If the project already has an ESLint config, surface the missing
rules as a diff and let the user opt in. For a fresh project, scaffold the config. Never
overwrite an existing config.

The defaults are evidence-based: drawn from a survey of ~35 reputable OSS suites that
actually run `eslint-plugin-playwright` / `eslint-plugin-cypress`, read config-by-config
(full extraction in `results/pr-campaign/lint-survey-{A,B,C,D,E,F}.txt`). Where real adoption
is split, the rule is labeled optional rather than shipped silently — say so when proposing.

## Playwright

### Ship — strongly evidenced
Extend the recommended preset, and set `forbidOnly` in CI. This is the part adopters agree on.

```js
// eslint.config.js (flat)
import playwright from 'eslint-plugin-playwright';

export default [
  {
    files: ['**/*.spec.ts', '**/*.test.ts', 'e2e/**/*.ts', 'tests/**/*.ts'],
    ...playwright.configs['flat/recommended'],
  },
];
```

```ts
// playwright.config.ts
export default defineConfig({
  forbidOnly: !!process.env.CI, // a committed test.only silently skips the rest of the file in CI
  // ...
});
```

`forbidOnly: !!process.env.CI` is the **dominant idiom** — about **15 of 17** surveyed plugin
adopters set it — and the strongest single signal in the data. Not exceptionless (tahowallet
hard-codes it `false`; lowdefy and openmct omit it), but ship it.

`flat/recommended` already enforces, **at error**, the rules that map to our worst smells:
`missing-playwright-await` (#15), `prefer-web-first-assertions` (#4c-4e), `no-focused-test`
(#7), `valid-expect` (bare matcher-less `expect`), plus `no-standalone-expect`,
`no-networkidle`, `no-wait-for-navigation`, `no-unsafe-references`, `no-unused-locators`,
`valid-expect-in-promise`, `valid-title`, `valid-describe-callback`. The baseline alone
covers the families that actually ship bugs green — so the baseline is the win; everything
below is opt-in.

### Optional add-ons — opinionated, partial adoption (label them when proposing)

```js
rules: {
  ...playwright.configs['flat/recommended'].rules,
  'playwright/no-wait-for-timeout': 'error',          // hard-sleep hygiene
  '@typescript-eslint/no-floating-promises': 'error', // needs type-aware config (parserOptions.project or projectService)
}
```

- **`no-wait-for-timeout`** — not enabled at error by `flat/recommended` in the plugin
  versions we surveyed (a newer plugin README marks it recommended at `warn`); a small minority
  escalates it (Kong + gestalt at error, OpenMetadata at warn ≈ **3 of 18**; a later wave of 7
  added none and one disabled it). Good hygiene; propose escalating to error as opt-in, not default.
- **`@typescript-eslint/no-floating-promises`** — catches floating `expect`s the Playwright
  rule can miss, and it is what microsoft/playwright runs on its own source. But on test files
  it is **essentially unused by plugin adopters (≈1 of 16)** and it needs a type-aware
  TypeScript-ESLint config (`parserOptions.project` or `projectService`). Ours by merit, not
  by consensus — say so.
- **Do NOT default `no-conditional-expect` to error.** **0 of 17** surveyed adopters elevate it;
  several (primer, fiftyone, anomalib) explicitly turn it off. The kibana precedent does not
  generalize.

## Cypress

`plugin:cypress/recommended` is the dominant baseline — every adopter wires it in. Be honest
about the rest, because the Cypress story is genuinely thinner:

- **No web-first-assertion equivalent exists.** None of the surveyed Cypress adopters (0 across
  every wave) have any rule that guards assertion correctness; Cypress retry-ability lives in the command chain, so nothing
  mirrors `prefer-web-first-assertions`. (Don't be fooled by `cypress/assertion-before-screenshot`,
  which ~6/8 adopters enable — it only requires *an* assertion before `cy.screenshot()`, not that
  a test asserts anything real.) This is the central asymmetry — Cypress assertion quality is
  `e2e-reviewer` territory, not lint.
- **Don't force the noisy rules to error.** Most adopters *relax* recommended (turn
  `no-unnecessary-waiting` / `unsafe-to-chain-command` off) rather than tighten it.
- **A focus ban is minority adoption** (~14 of 17 have none) but present in flagship repos —
  forem, mattermost focalboard, and pachyderm all ban it, **all via `no-only-tests`**. The native
  `cypress/no-only` is **dead (0 usage across every wave)** and `mocha/no-exclusive-tests` is only
  used by cypress-io itself. So if you add a focus ban, use `no-only-tests` and frame it as opt-in
  parity with Playwright's `no-focused-test`, not a community norm.

```js
// .eslintrc.js
module.exports = {
  extends: ['plugin:cypress/recommended'],  // strongly evidenced baseline
  plugins: ['no-only-tests'],
  rules: {
    'no-only-tests/no-only-tests': 'error',  // opt-in focus ban — what flagship adopters (forem, focalboard, pachyderm) use
  },
};
```

## Anti-pattern coverage map (what lint prevents vs what it cannot)

| Anti-pattern | Prevented by | Notes |
|---|---|---|
| #15 missing `await` on web-first matcher | `playwright/missing-playwright-await` (error, recommended); optionally `@typescript-eslint/no-floating-promises` | the TS rule is an extra catch-all, not a default |
| #4c-4e one-shot state/content reads | `playwright/prefer-web-first-assertions` (error, recommended) | Playwright only; no Cypress equivalent |
| #7 committed `it.only`/`describe.only` | `playwright/no-focused-test` + `forbidOnly` (PW); `no-only-tests` (Cypress, opt-in) | config-level `forbidOnly` is the strongest backstop |
| bare matcher-less `expect(locator)` | `playwright/valid-expect` (error, recommended) | requires a matcher |
| hard sleeps / `waitForTimeout` / networkidle | `playwright/no-wait-for-timeout` (optional) + `no-networkidle` (recommended); `cypress/no-unnecessary-waiting` | |
| #5b `force: true` clicks | `playwright/no-force-option` (warn, recommended) | no clean Cypress rule |

**Not covered by off-the-shelf recommended lint — these still need `e2e-reviewer`, the
scanner's Tier-3, or a custom `no-restricted-syntax` rule:**

- **#4f locator-as-truthy** (`expect(page.locator('.x')).toBeTruthy()` — a bare locator with
  no method call) — no off-the-shelf rule fires; a true silent-always-pass only semantic review
  catches. (Note: the *method* form `expect(loc.isDisabled()).toBeTruthy()` IS flagged by
  `prefer-web-first-assertions`; it's the bare locator-as-truthy form that slips through lint.)
- **#3 `.catch(() => false)` swallow** and **#3b blanket
  `cy.on('uncaught:exception', () => false)`** — no lint rule; scanner Tier-3 / reviewer.
- Name-assertion mismatch, missing-Then, YAGNI/zombie specs, POM consistency — semantic.

Frame the proposal honestly: lint is the every-commit guardrail for the commodity smells;
`e2e-reviewer` covers the silent-always-pass families and the judgment no rule can express.

## Sources

~50 reputable OSS suites (8 survey waves, incl. an adversarial counter-search) that actually
run the plugins, read config-by-config (not guessed).
Playwright baseline = `eslint-plugin-playwright` `recommended`. PW adopters incl. elastic/kibana,
Kong/insomnia, OpenMetadata, n8n, storybook, primer/react, gestalt, fiftyone, suitenumerique/docs,
nasa/openmct, daedalOS, waku, plausible, hyperdx, ng-bootstrap, elementor, anomalib, iptvnator.
Tally (~17 PW plugin adopters): `forbidOnly` ~15/17; `no-wait-for-timeout` ~3/18 (one wave 0/7);
`no-conditional-expect` elevated 0/17 (several disable); `no-floating-promises` on test files ≈1/16.
Cypress adopters (~17) incl. react-hook-form, redash, shepherd, barba, why-did-you-render,
Semantic-UI-React, metabase, appsmith, vue-cli, react-admin, pageplug, bookshelf;
`plugin:cypress/recommended` is the common baseline (many wire it globals-only); focus-ban absent
in ~14/17; `cypress/no-only` 0 usage across all waves; focus-banners (forem, focalboard, pachyderm) all use
`no-only-tests`; 0 of ~17 have any assertion-correctness rule. An adversarial counter-search
(waves G/H) found no ≥2k-star repo that elevates `no-conditional-expect` or adds a real assertion
rule, so no ship/optional/drop call changed. Full extraction:
`results/pr-campaign/lint-survey-{A,B,C,D,E,F,G,H}.txt`.

# Upstream E2E Rule Sources

This inventory records methodology provenance. `e2e-skills` does not vendor upstream source and does not require these packages.

The scanner's disabled-by-default registry fallback requests an exact, jointly
reviewed tool set: ESLint 10.8.0, eslint-plugin-playwright 2.11.0,
eslint-plugin-cypress 6.4.3, @typescript-eslint/parser 8.65.0, TypeScript 6.0.3,
eslint-plugin-cypress-silent-pass 0.2.2, and eslint-plugin-mocha 12.0.1. These
pins are one compatibility boundary: update them together only after the local
ESLint path, scanner scope, and security contracts pass. Only these direct
versions are pinned — npm resolves each package's transitive closure from its own
semver ranges at scan time and the scanner ships no lockfile, so that closure is
not integrity-pinned; install lifecycle scripts are disabled to bound the
exposure. Offline operation and the bundled Tier 2/Tier 3 fallback never depend
on this optional download.

## Playwright ESLint precedent

Source: [eslint-plugin-playwright](https://github.com/mskelton/eslint-plugin-playwright), MIT.

Correctness families map to existing taxonomy: awaited Playwright calls (#15/#16), focused tests (#7), conditional verification (#3/#5), force bypass (#5b), raw/evaluated DOM and legacy page APIs (#6/#17), arbitrary waits and network-idle (#9), positional or unsafe locators (#10), missing or unused verification (#8), and one-shot or unnecessary assertions (#4). Rules about title casing, spacing, hook placement, tag formatting, maximum counts, or organization are project style and stay out of the taxonomy.

## Cypress ESLint precedent

Source: [eslint-plugin-cypress](https://github.com/cypress-io/eslint-plugin-cypress), MIT.

Correctness families map to focused tests (#7), arbitrary waits (#9), forced interactions (#5b), conditional or discarded verification (#5/#8), brittle selector and chain behavior (#10), and screenshot-without-outcome review (#2). Rules mandating one selector convention (`require-data-selectors`, XPath bans) or one chaining style are project conventions unless the concrete usage creates an existing P0/P1 smell.

## Runtime falsification precedent

- [playwright-mutation-gate](https://github.com/VladyslavDmitriiev/playwright-mutation-gate), MIT: assertion inversion and behavior mutation informed V2/V3. Optional external implementation, not a dependency.
- [ai-qa-pipeline](https://github.com/VladyslavDmitriiev/ai-qa-pipeline), license per upstream repository: independent writer/judge roles, bounded repair, scratch candidates, human promotion, and post-debug review informed V1/V6. No pipeline code is copied.
- [StrykerJS](https://stryker-mutator.io/docs/stryker-js/introduction/): mutation testing changes code and checks whether existing tests detect it, supporting V3's targeted-fault rationale. Not a dependency; a general JavaScript mutation workflow is not evidence that arbitrary browser-app mutations are safe or causally attributable.

## AI-assisted review workflow precedent

- [Cypress AI Test Generation](https://docs.cypress.io/app/guides/ai-test-generation): `cy.prompt()` steps, generated-code export, selector healing. Generated code is reviewable output, not proof that generated tests capture intended behavior or replace an independent oracle.
- [Cypress Branch Review](https://docs.cypress.io/cloud/features/branch-review): compares pull-request results against the base branch before merge — the precedent for the introduced/worsened/pre-existing distinction, and the reason static and runtime evidence are recorded separately. Cypress Cloud-specific: neither a local-runner contract nor a required service.

## Generated-test oracle and vendor contracts

- [Vitest: Writing Tests with AI](https://vitest.dev/guide/learn/writing-tests-with-ai#do-the-tests-actually-assert-something-meaningful) warns that no-throw and mock-focused checks give false confidence. Unit-test guidance for the same oracle boundary, not an E2E accuracy result.
- [Playwright ARIA snapshot partial matching](https://playwright.dev/docs/aria-snapshots#partial-matching): omitting a control's accessible name lets any label match. Upstream contract for #4j; it does not mean snapshots omit names by default.
- [Playwright best practices](https://playwright.dev/docs/best-practices) prioritizes user-visible behavior, user-facing locators, and explicit contracts; [Playwright assertions](https://playwright.dev/docs/test-assertions) documents retrying async assertions. Retryability reduces timing noise but cannot make a weak or wrong postcondition meaningful.
- [Playwright Test Agents](https://playwright.dev/docs/test-agents#-generator) verifies generated selectors and assertions live. Its sample uses direct page locators, but the docs do not establish POM drift as a default outcome.
- [Cypress Studio AI](https://docs.cypress.io/app/guides/cypress-studio#types-of-assertions-studio-ai-recommends) states its recommendations reflect visible UI changes with no access to application code, business logic, or backend rules. DOM-delta assertions still need an independent behavior oracle.
- [Cypress conditional testing](https://docs.cypress.io/app/guides/conditional-testing) requires stabilized state and a non-mutable source of truth — the upstream contract behind treating DOM-dependent runtime gates as bypass risks rather than ordinary branching.
- [Playwright MCP versus CLI](https://github.com/microsoft/playwright-mcp/blob/55679f5f3d4b4f3e2534ec0ce2fc5683ba2eaf3f/README.md#playwright-mcp-vs-playwright-cli) suggests coding agents may benefit from CLI plus skills for token efficiency while retaining MCP for persistent, exploratory loops. Vendor guidance, not a universal benchmark.

The repository's full [59-source evidence ledger](https://github.com/voidmatcha/e2e-skills/blob/main/docs/llm-generated-e2e-test-evidence.md) records verified, qualified, and not-cleared claims with denominators and E2E extrapolation limits. Use that evidence to choose falsification rules, never to claim a model accuracy rate.

## Adoption rule

Import semantics only when they protect correctness, diagnosability, isolation, or silent-pass safety and can be expressed by an existing stable pattern or V-rule. Do not import style-only rules, auto-healing behavior, package installation, or cloud-service requirements. Every new mechanical detector still needs a true-positive fixture and an exact-line false-positive guard.

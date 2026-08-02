# Upstream E2E Rule Sources

This inventory records methodology provenance. `e2e-skills` does not vendor upstream source and does not require these packages.

The scanner's disabled-by-default registry fallback requests an exact, jointly
reviewed tool set: ESLint 10.8.0, eslint-plugin-playwright 2.11.0,
eslint-plugin-cypress 6.4.3, @typescript-eslint/parser 8.65.0, TypeScript 6.0.3,
eslint-plugin-cypress-silent-pass 0.2.2, and eslint-plugin-mocha 12.0.1. These
pins are one compatibility boundary: update them together only after the local
ESLint path, scanner scope, and security contracts pass. Only these direct
versions are pinned. npm resolves each package's transitive dependencies from
their own semver ranges at scan time and the scanner ships no lockfile, so the
closure is not integrity-pinned; the download runs with install lifecycle
scripts disabled to bound that exposure. Offline operation and
the bundled Tier 2/Tier 3 fallback do not depend on this optional download path.

## Playwright ESLint precedent

Source: [eslint-plugin-playwright](https://github.com/mskelton/eslint-plugin-playwright), MIT.

Locally relevant correctness families are mapped to existing taxonomy: awaited Playwright calls (#15/#16), focused tests (#7), conditional verification (#3/#5), force bypass (#5b), raw/evaluated DOM and legacy page APIs (#6/#17), arbitrary waits/network-idle (#9), positional or unsafe locators (#10), missing/unused verification (#8), and one-shot or unnecessary assertions (#4). Rules concerned only with title casing, spacing, hook placement, tag formatting, maximum counts, or organization remain project style and are not copied into the smell taxonomy.

## Cypress ESLint precedent

Source: [eslint-plugin-cypress](https://github.com/cypress-io/eslint-plugin-cypress), MIT.

Locally relevant correctness families are mapped to focused tests (#7), arbitrary waits (#9), forced interactions (#5b), conditional/discarded verification (#5/#8), brittle selector/chain behavior (#10), and screenshot-without-outcome review (#2). Rules that mandate one selector convention (`require-data-selectors`, XPath bans) or one chaining style are treated as project conventions unless the concrete usage creates an existing P0/P1 smell.

## Runtime falsification precedent

- [playwright-mutation-gate](https://github.com/VladyslavDmitriiev/playwright-mutation-gate), MIT: assertion inversion and behavior mutation informed V2/V3. It is an optional external implementation, not a dependency.
- [ai-qa-pipeline](https://github.com/VladyslavDmitriiev/ai-qa-pipeline), license per upstream repository: independent writer/judge roles, bounded repair, scratch candidates, human promotion, and post-debug review informed V1/V6. No agent CLI or pipeline code is copied.

## Generated-test oracle and vendor contracts

- [Vitest: Writing Tests with AI](https://vitest.dev/guide/learn/writing-tests-with-ai#do-the-tests-actually-assert-something-meaningful) warns that no-throw and mock-focused checks give false confidence. Treat this as unit-test guidance for the same oracle boundary, not an E2E accuracy result.
- [Playwright ARIA snapshot partial matching](https://playwright.dev/docs/aria-snapshots#partial-matching) states that omitting a control's accessible name allows any label to match. This is the upstream contract for #4j; it does not mean every ARIA snapshot omits names by default.
- [Playwright best practices](https://playwright.dev/docs/best-practices) prioritizes user-visible behavior, user-facing locators, and explicit contracts, while [Playwright assertions](https://playwright.dev/docs/test-assertions) documents retrying async assertions. Retryability reduces timing noise but cannot make a weak or wrong postcondition meaningful.
- [Playwright Test Agents](https://playwright.dev/docs/test-agents#-generator) verifies generated selectors and assertions live. Its published sample uses direct page locators, but the documentation does not establish that POM drift is a default outcome.
- [Cypress Studio AI](https://docs.cypress.io/app/guides/cypress-studio#types-of-assertions-studio-ai-recommends) says its recommendations reflect visible UI changes and do not have access to application code, business logic, or backend rules. DOM-delta assertions therefore still need an independent behavior oracle.
- [Cypress conditional testing](https://docs.cypress.io/app/guides/conditional-testing) requires stabilized state and recommends a non-mutable source of truth. This is the upstream contract behind treating DOM-dependent runtime gates as bypass risks rather than ordinary branching.
- [Playwright MCP versus CLI](https://github.com/microsoft/playwright-mcp/blob/55679f5f3d4b4f3e2534ec0ce2fc5683ba2eaf3f/README.md#playwright-mcp-vs-playwright-cli) says coding agents might benefit from CLI plus skills for token efficiency while retaining MCP for persistent, exploratory, and richly introspective loops. This is vendor guidance, not a universal benchmark.

The repository's full [59-source evidence ledger](https://github.com/voidmatcha/e2e-skills/blob/main/docs/llm-generated-e2e-test-evidence.md) records verified, qualified, and not-cleared claims with denominators and E2E extrapolation limits. The public skill should use that evidence to choose falsification rules, never to claim a model accuracy rate.

## Adoption rule

Import semantics only when they protect correctness, diagnosability, isolation, or silent-pass safety and can be expressed by an existing stable pattern or V-rule. Do not import style-only rules, auto-healing behavior, package installation, or cloud-service requirements. Every new mechanical detector still needs a true-positive fixture and an exact-line false-positive guard.

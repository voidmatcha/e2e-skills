# Local E2E Rule Bridge

`e2e-skills` carries its correctness rules locally. A generated suite must not depend on ESLint, a plugin, `npx`, or a package download to receive the same core review on every host.

## Existing project rules

Discover testing docs, package scripts, ESLint config, Playwright/Cypress config, CI workflows, custom fixtures/commands, and seed specs. When the project already has an E2E lint command, run that exact repository-native command and merge its results with `e2e-reviewer`:

- Equivalent rule: one finding with both provenance sources.
- Project rule is stronger: follow it for generated style/conventions.
- e2e-skills semantic rule is stronger: keep the finding; lint green does not prove intent.
- Conflict: P0 silent-pass safety wins. P1 requires concrete justification to suppress; P2/style follows documented project convention.

Never install, scaffold, or rewrite a lint configuration unless the user explicitly requests that separate change.

## Local semantic coverage

The bundled scanner/reviewer owns these correctness families regardless of project lint:

| Local contract | Related upstream precedent | Local taxonomy |
|---|---|---|
| awaited Playwright assertions/actions | `missing-playwright-await` | #15/#16 |
| no focused test leaks | `no-focused-test`, Mocha exclusive-test rules | #7 |
| no arbitrary waits/network-idle crutches | `no-wait-for-timeout`, `no-networkidle`, `no-unnecessary-waiting` | #9 |
| web-first/retryable assertions | `prefer-web-first-assertions` | #4c–#4e |
| no locator-as-truthy assertions | `no-unnecessary-assertions`; Cypress silent-pass precedent | #4f |
| no unjustified forced interaction | `no-force-option`, `cypress/no-force` | #5b |
| no conditional/suppressed verification | `no-conditional-expect`, `no-conditional-in-test` | #3/#5 |
| no unused/discarded verification | `expect-expect`, `no-unused-locators`, Cypress return-value rules | #8 |
| stable locator and chain discipline | locator/nth/unsafe-chain precedents | #6/#10/#17 |

The local implementation is independent and does not copy plugin source. Upstream rules are references and optional additional enforcement when a project already uses them.

## What remains semantic

No single-file lint rule can reliably decide test-title/behavior alignment, missing business post-state, auth preconditions, optimistic UI versus write success, real-backend safety, fixture render guards, or whether a fault probe should turn the test red. These remain `e2e-reviewer` and V1–V6 responsibilities.

## Generator behavior

Use existing safe project conventions as the style reference. Do not copy an existing P0/P1 pattern merely because it is common in the suite. Report missing project lint only as informational context; local review remains the gate.

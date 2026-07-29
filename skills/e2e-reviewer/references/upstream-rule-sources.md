# Upstream E2E Rule Sources

This inventory records methodology provenance. `e2e-skills` does not vendor upstream source and does not require these packages.

## Playwright ESLint precedent

Source: [eslint-plugin-playwright](https://github.com/mskelton/eslint-plugin-playwright), MIT.

Locally relevant correctness families are mapped to existing taxonomy: awaited Playwright calls (#15/#16), focused tests (#7), conditional verification (#3/#5), force bypass (#5b), raw/evaluated DOM and legacy page APIs (#6/#17), arbitrary waits/network-idle (#9), positional or unsafe locators (#10), missing/unused verification (#8), and one-shot or unnecessary assertions (#4). Rules concerned only with title casing, spacing, hook placement, tag formatting, maximum counts, or organization remain project style and are not copied into the smell taxonomy.

## Cypress ESLint precedent

Source: [eslint-plugin-cypress](https://github.com/cypress-io/eslint-plugin-cypress), MIT.

Locally relevant correctness families are mapped to focused tests (#7), arbitrary waits (#9), forced interactions (#5b), conditional/discarded verification (#5/#8), brittle selector/chain behavior (#10), and screenshot-without-outcome review (#2). Rules that mandate one selector convention (`require-data-selectors`, XPath bans) or one chaining style are treated as project conventions unless the concrete usage creates an existing P0/P1 smell.

## Runtime falsification precedent

- [playwright-mutation-gate](https://github.com/VladyslavDmitriiev/playwright-mutation-gate), MIT: assertion inversion and behavior mutation informed V2/V3. It is an optional external implementation, not a dependency.
- [ai-qa-pipeline](https://github.com/VladyslavDmitriiev/ai-qa-pipeline), license per upstream repository: independent writer/judge roles, bounded repair, scratch candidates, human promotion, and post-debug review informed V1/V6. No agent CLI or pipeline code is copied.

## Adoption rule

Import semantics only when they protect correctness, diagnosability, isolation, or silent-pass safety and can be expressed by an existing stable pattern or V-rule. Do not import style-only rules, auto-healing behavior, package installation, or cloud-service requirements. Every new mechanical detector still needs a true-positive fixture and an exact-line false-positive guard.

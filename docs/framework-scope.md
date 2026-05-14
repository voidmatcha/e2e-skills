# Framework Scope

## Supported Deeply

| Framework | Status | What is covered |
|-----------|--------|-----------------|
| Playwright | First-class | Generation, static review, report debugging, locator guidance, web-first assertions, traces, auth, network waits |
| Cypress | First-class for review/debug | Static review, mochawesome/JUnit debugging, retryability, `cy.intercept`, `cy.session`, screenshots/videos |

## Not In Scope Today

Puppeteer is intentionally not listed as supported automation. The general review ideas still apply, but the repository does not currently ship Puppeteer-specific grep patterns, eval fixtures, or debugger workflows.

## Why Keep The Scope Narrow

E2E failures are framework-specific. A broad checklist that claims to support every runner usually misses the sharp edges that matter: Playwright web-first assertions, Cypress command retryability, framework-specific auth/session setup, and framework-specific report artifacts.

New framework support should include all of the following before it is advertised:

1. Grep patterns or mechanical checks.
2. At least one eval file with true positives and false positive guards.
3. Report/debug artifact handling if the framework has a debugger skill.
4. README and marketplace metadata updates.

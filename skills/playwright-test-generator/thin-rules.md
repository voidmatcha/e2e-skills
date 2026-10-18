---
name: playwright-thin-rules
description: Apply a compact checklist for stable Playwright locators, meaningful assertions, readable specs, and verified delivery alongside the official generator.
---

# Playwright thin rules

- [ ] Prefer locators by role and accessible name, associated label, configured test id, or visible text; use observed semantics so controls stay identifiable.
- [ ] Never select by CSS id or styling class, including attribute-selector equivalents; presentation details do not identify user behaviour.
- [ ] Scope repeated text through a meaningful ancestor or filter; this identifies intent without relying on element order.
- [ ] Use `.nth()`, `.first()`, or `.last()` only with `// JUSTIFIED: <reason>` immediately above the locator explaining why position is required; ordering otherwise hides ambiguity.
- [ ] Await Playwright actions and retrying web-first assertions; this keeps steps ordered and lets asynchronous outcomes settle.
- [ ] Assert the promised observable outcome or ARIA state; never use `toHaveClass` or styling-class checks to prove state because appearance is not the product contract.
- [ ] For an operation with an explicit ownership or filtering boundary, include an unaffected witness outside that boundary and verify that it remains unchanged.
- [ ] Wait for an observable condition, never a hard sleep or `waitForTimeout`; readiness varies across machines.
- [ ] Reject vacuous checks, including locator truthiness and constant assertions such as `expect(true)`; an assertion must fail when the promised outcome is absent.
- [ ] Give every test a title describing its action and expected behaviour; never use generic numbered placeholders because failures need useful names.
- [ ] Group related behaviours of one screen in one spec file while keeping tests independent; this makes coverage and shared setup readable.
- [ ] Run the generated tests at least once with the project's existing command and fix failures before finishing; execution reveals errors that source inspection misses.

---
max_turns: 20
allowed_tools: [Read, Glob, Grep, Skill]
---

Our Playwright test started failing in CI and I need to know why. There is no playwright-report directory in this workspace; here is the failure output:

```text
  1) [chromium] › tests/profile.spec.ts:12:5 › saves the avatar ──────────────
    Error: Timed out 5000ms waiting for expect(locator).toBeVisible()
    Locator: getByTestId('avatar-saved')
    Expected: visible
    Received: <element(s) not found>
       at tests/profile.spec.ts:18:47
    Retry #1 passed.
```

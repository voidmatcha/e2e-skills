---
max_turns: 30
allowed_tools: [Read, Glob, Grep, Skill]
---

Please review this Playwright test from our checkout suite for anti-patterns and assertions that could pass silently. It is `tests/checkout.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

test.only('applies the loyalty discount at checkout', async ({ page }) => {
  await page.goto('/cart');
  await page.getByRole('button', { name: 'Checkout' }).click();
  await page.waitForTimeout(3000);
  expect(page.getByTestId('discount-line')).toBeVisible();
});
```

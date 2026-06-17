import { test, expect } from '@playwright/test';

// Fixture for the #15 "awaited locator" variant: the await is misplaced INSIDE expect()
// onto the locator (a no-op) instead of on expect itself, so the web-first matcher promise
// floats and the assertion never settles. Includes false-positive guards.

test('opens the dialog', async ({ page }) => {
  await page.goto('/');
  // BUG (#15): await is on the locator, not on expect -> matcher promise unawaited.
  expect(await page.getByTestId('run-dialog')).toBeVisible();
  expect(await page.getByText('Saved')).toHaveText('Saved');
});

test('valid awaited expects are not flagged', async ({ page }) => {
  await page.goto('/');
  // OK: await is on expect (correct web-first form) -> must NOT be flagged as #15.
  await expect(page.getByTestId('run-dialog')).toBeVisible();
  await expect(page.getByText('Saved')).toHaveText('Saved');
});

test('value-resolving reads belong to #4c-4e not #15', async ({ page }) => {
  await page.goto('/');
  // This is the one-shot read anti-pattern (#4c-4e), NOT the awaited-locator #15 variant.
  expect(await page.locator('.row').isVisible()).toBe(true);
  // Numeric read with a non-web-first matcher must NOT be flagged by either #15 form.
  expect(await page.locator('.row').count()).toBeGreaterThan(0);
});

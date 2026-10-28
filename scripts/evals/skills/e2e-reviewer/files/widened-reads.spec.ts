import { test, expect } from '@playwright/test';

test('discarded page-level visibility check with a selector', async ({ page }) => {
  await page.goto('/dashboard');
  await page.isVisible('[data-testid="create-organization-btn"]');
  await page.locator('[data-testid="create-organization-btn"]').click();
});

test('one-shot all text contents read', async ({ page }) => {
  await page.goto('/home');
  expect(await page.locator('h2').allTextContents()).toContain('Home');
});

test('guards that must not be flagged as #8b', async ({ page }) => {
  await page.goto('/x');
  const present = await page.isVisible('.banner');
  if (present) {
    await expect(page.locator('.banner')).toBeVisible();
  }
  await page.locator('.err').isVisible().catch(() => false);
});

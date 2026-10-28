import { test, expect } from '@playwright/test';

test.describe('Cookie consent', () => {
  test('dismisses the cookie banner when shown', async ({ page }) => {
    await page.goto('/');
    if (await page.locator('[data-testid="cookie-banner"]').isVisible()) {
      await page.click('[data-testid="cookie-accept"]');
      await expect(page.locator('[data-testid="cookie-banner"]')).toBeHidden();
    }
  });

  test('cookie banner links to the privacy policy', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('[data-testid="cookie-banner"] a[href="/privacy"]')).toBeVisible();
  });

  test('shows account menu when logged in and sign-in button otherwise', async ({ page }) => {
    await page.goto('/');
    if (await page.locator('[data-testid="account-menu"]').isVisible()) {
      await expect(page.locator('[data-testid="account-menu"]')).toContainText('My account');
    } else {
      await expect(page.locator('[data-testid="sign-in"]')).toBeVisible();
    }
  });
});

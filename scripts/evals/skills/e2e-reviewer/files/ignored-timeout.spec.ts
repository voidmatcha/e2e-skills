import { test, expect } from '@playwright/test';

test('dismisses the cookie banner when shown', async ({ page }) => {
  await page.goto('/');
  const banner = page.getByRole('dialog', { name: 'Cookies' });
  if (await banner.isVisible({ timeout: 5000 })) {
    await banner.getByRole('button', { name: 'Accept' }).click();
  }
  await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible();
});

test('waits for the cookie banner before accepting', async ({ page }) => {
  await page.goto('/');
  const banner = page.getByRole('dialog', { name: 'Cookies' });
  await expect(banner).toBeVisible({ timeout: 5000 });
  await banner.getByRole('button', { name: 'Accept' }).click();
  await banner.waitFor({ state: 'hidden', timeout: 5000 });
});

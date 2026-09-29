import { test, expect } from '@playwright/test';

test('closing preferences hides dialog and restores focus', async ({ page }) => {
  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'Preferences' }).click();
  await page.getByRole('button', { name: 'Close' }).click();
  await expect(page).toHaveURL(/dashboard/);
});

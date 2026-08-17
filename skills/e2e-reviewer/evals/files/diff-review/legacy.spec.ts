import { expect, test } from '@playwright/test';

test.only('legacy smoke still opens dashboard', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
});

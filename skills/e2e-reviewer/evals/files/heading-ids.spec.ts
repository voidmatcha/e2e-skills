import { test, expect } from '@playwright/test';

test.only('shows the saved banner', async ({ page }) => {
  await page.goto('/settings');
  await page.getByRole('button', { name: 'Save' }).click();
  await page.waitForTimeout(2000);
  await expect(page.getByText('Saved')).toBeVisible();
});

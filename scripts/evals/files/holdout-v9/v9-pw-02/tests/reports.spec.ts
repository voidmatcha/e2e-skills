import { test, expect } from '@playwright/test';

test('lists the three quarterly reports', async ({ page }) => {
  await page.goto('/reports');
  await expect(page.locator('.loading-spinner')).toBeHidden();
  await expect(page.getByTestId('report-row')).toHaveCount(3);
});

test('dismisses the upgrade banner', async ({ page }) => {
  await page.goto('/reports');
  await page.getByRole('button', { name: 'Dismiss upgrade offer', exact: true }).click();
  await expect(page.locator('.upgrade-banner')).not.toBeVisible();
});

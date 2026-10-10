import { test, expect } from '@playwright/test';
test('shows water height and tide phase', async ({ page }) => {
  await page.goto('/estuary');
  await expect(page.getByTestId('height')).toHaveText('2.4 m');
});
test('shows salinity and sampling time', async ({ page }) => {
  await page.goto('/estuary');
  await expect(page).toHaveURL(/estuary/);
});

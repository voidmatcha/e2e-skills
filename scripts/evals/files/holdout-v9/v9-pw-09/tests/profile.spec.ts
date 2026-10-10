import { test, expect } from '@playwright/test';

test('saves the new display name to the profile', async ({ page }) => {
  await page.route('**/api/profile', (route) => route.fulfill({ status: 204 }));
  await page.goto('/settings/profile');
  await page.getByLabel('Display name', { exact: true }).fill('Rin Okafor');
  await page.getByRole('button', { name: 'Save profile', exact: true }).click();
  await expect(page.getByTestId('profile-heading')).toHaveText('Rin Okafor');
});

test('turns on the compact layout toggle', async ({ page }) => {
  await page.goto('/settings/profile');
  await page.getByRole('button', { name: 'Compact layout', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Compact layout', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

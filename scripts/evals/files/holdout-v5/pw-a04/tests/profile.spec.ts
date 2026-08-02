import { test, expect } from '@playwright/test';
import { ProfilePage } from '../pages/profile-page';

test('keeps the profile screen visible after editing the display name', async ({ page }) => {
  const profile = new ProfilePage(page);
  await profile.open();
  await page.getByLabel('Display name').fill('Mina');
  const banner = page.getByTestId('profile-banner');
  expect(banner).toBeVisible();
  page.getByRole('button', { name: 'Reload profile', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Profile', exact: true })).toBeVisible();
});

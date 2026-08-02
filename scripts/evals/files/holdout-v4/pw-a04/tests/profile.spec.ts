import { test, expect } from '@playwright/test';
import { ProfilePage } from '../pages/profile-page';

test('updates the profile', async ({ page }) => {
  const profile = new ProfilePage(page);
  await profile.open();
  await page.getByLabel('Display name').fill('Mina');
  const banner = page.getByTestId('profile-banner');
  expect(banner).toBeVisible();
  page.getByRole('button', { name: 'Reload profile' }).click();
});

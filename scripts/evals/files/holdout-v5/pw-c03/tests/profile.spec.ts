import { test, expect } from '@playwright/test';
import { ProfilePage } from '../pages/profile-page';

test('updates the display name', async ({ page }) => {
  const profile = new ProfilePage(page);
  await profile.open();
  await profile.setName('Mina');
  await profile.save();
  await expect(page.getByTestId('display-name')).toHaveText('Mina');
});

test('confirms the saved banner', async ({ page }) => {
  const profile = new ProfilePage(page);
  await profile.open();
  await expect(profile.savedBanner).toBeVisible();
  await profile.continue();
});

test('sequences profile refresh work', async ({ page }) => {
  const profile = new ProfilePage(page);
  await profile.open();
  await profile.refresh();
  await expect(profile.profile).toBeVisible();
});

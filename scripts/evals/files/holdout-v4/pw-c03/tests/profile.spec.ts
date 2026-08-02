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
  await page.goto('/profile');
  await expect(page.getByTestId('saved-banner')).toBeVisible();
  await page.getByRole('button', { name: 'Continue' }).click();
});

test('sequences profile refresh work', async ({ page }) => {
  await Promise.all([
    page.getByRole('button', { name: 'Refresh' }).click(),
    page.waitForResponse('/api/profile'),
  ]);
  await expect(page.getByTestId('profile')).toBeVisible();
});

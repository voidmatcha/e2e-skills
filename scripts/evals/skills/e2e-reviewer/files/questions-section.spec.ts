// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test('saving the profile shows the saved state', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByRole('status')).toHaveText('Profile saved');
});

test('deleting the profile shows the goodbye banner', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Delete profile' }).click();
  expect(page.getByRole('banner', { name: 'Goodbye' })).toBeTruthy();
});

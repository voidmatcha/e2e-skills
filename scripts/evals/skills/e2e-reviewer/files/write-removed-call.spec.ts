// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test('saving the profile shows the saved state', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByRole('status')).toHaveText('Profile saved');
});

test('saving the profile stores the new name', async ({ page }) => {
  await page.goto('/profile');
  await page.getByLabel('Display name').fill('Mina');
  const saved = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().endsWith('/api/profile'));
  await page.getByRole('button', { name: 'Save profile' }).click();
  expect((await saved).ok()).toBe(true);
  await page.reload();
  await expect(page.getByLabel('Display name')).toHaveValue('Mina');
});

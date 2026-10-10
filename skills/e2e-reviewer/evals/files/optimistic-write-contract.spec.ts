import { test, expect } from '@playwright/test';

test('saving a profile sends PATCH /api/profile', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByRole('status')).toHaveText('Saved');
});

test('save control shows immediate feedback', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByRole('status')).toHaveText('Saved');
});

test('saved display name persists', async ({ page }) => {
  await page.goto('/profile');
  await page.getByLabel('Display name').fill('Ada');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await page.reload();
  await expect(page.getByLabel('Display name')).toHaveValue('Ada');
});

import { test, expect } from '@playwright/test';

test('canceling edit restores summary and hides editor', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Edit' }).click();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByTestId('profile-summary')).toBeVisible();
});

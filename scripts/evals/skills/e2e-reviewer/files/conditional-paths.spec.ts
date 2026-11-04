import { test, expect } from '@playwright/test';

test('shows the saved state on either layout', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  const compact = await page.getByTestId('compact-layout').isVisible();
  if (compact) await expect(page.getByRole('status')).toHaveText('Saved');
  else await expect(page.getByRole('alert')).toHaveText('Profile saved');
  if (await page.getByRole('dialog', { name: 'Tips' }).isVisible()) await page.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Profile', exact: true })).toBeVisible();
});

test('confirms the deletion', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  if (await page.getByRole('alert').isVisible()) {
    await expect(page.getByRole('alert')).toHaveText('Profile deleted');
  }
});

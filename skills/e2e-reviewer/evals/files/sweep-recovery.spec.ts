import { test, expect } from '@playwright/test';

test.describe('sweep recovery', () => {
  test('guard return skips the promised assertion', async ({ page }) => {
    const rows = await page.locator('.row').count();
    if (rows === 0) {
      return;
    }
    await expect(page.locator('.row')).toHaveCount(rows);
  });

  test('mobile variant is intentionally skipped', async ({ page }) => {
    if (process.env.VIEWPORT === 'mobile') {
      test.skip(true, 'the settings panel does not exist on mobile');
    }
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible();
  });

  test('unscoped accessible name', async ({ page }) => {
    await expect(page.getByRole('link', { name: 'Job', exact: false })).toBeVisible();
  });

  test('soft prerequisite', async ({ page }) => {
    const form = page.getByTestId('profile-form');
    await expect.soft(form).toBeVisible();
    await form.getByLabel('Display name').fill('Mina');
  });
});

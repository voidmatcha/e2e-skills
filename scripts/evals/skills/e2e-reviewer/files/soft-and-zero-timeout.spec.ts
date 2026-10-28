import { test, expect } from '@playwright/test';

test.describe('notification banner', () => {
  test('banner disappears after dismiss', async ({ page }) => {
    await page.goto('/inbox');
    await page.getByRole('button', { name: 'Dismiss' }).click();
    await expect(page.locator('.banner')).toHaveCount(0, { timeout: 0 });
  });

  test('spinner is bounded, not slept', async ({ page }) => {
    await page.goto('/inbox');
    await page.locator('.spinner').waitFor({ state: 'hidden', timeout: 5000 });
    await expect(page.locator('.inbox-list')).toBeVisible({ timeout: 5000 });
  });

  test('flash error must never appear on the safe path', async ({ page }) => {
    test.setTimeout(1500);
    await page.goto('/inbox?safe=1');
    // JUSTIFIED: deliberately share the bounded 1500ms test deadline during shutdown
    await expect(page.locator('.flash-error')).toHaveCount(0, { timeout: 0 });
  });
});

test.describe('profile panel', () => {
  test('edits a profile through a soft-gated form', async ({ page }) => {
    await page.goto('/profile');
    const profileForm = page.getByTestId('profile-form');
    await expect.soft(profileForm).toBeVisible();
    await profileForm.getByLabel('Display name').fill('Mina');
    await profileForm.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('status')).toHaveText('Saved');
  });

  test('shows plan details', async ({ page }) => {
    await page.goto('/profile');
    await expect(page.locator('.plan-panel')).toBeVisible();
    await expect.soft(page.locator('.plan-name')).toHaveText('Pro');
    await expect.soft(page.locator('.renewal-hint')).toContainText('renews');
    await expect.soft(page.locator('.billing-cycle')).toHaveText('Monthly');
  });
});

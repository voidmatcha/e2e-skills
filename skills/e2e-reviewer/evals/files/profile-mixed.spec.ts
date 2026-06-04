import { test, expect } from '@playwright/test';

test.describe('Profile', () => {
  test.use({ storageState: 'playwright/.auth/user.json' });

  test.beforeEach(async ({ page }) => {
    // Network can be slow on first cold start; retry the initial nav once.
    try {
      await page.goto('/profile');
      await expect(page.getByTestId('profile-root')).toBeVisible();
    } catch (e) {
      await page.goto('/profile');
      await expect(page.getByTestId('profile-root')).toBeVisible();
    }
  });

  test('updates display name', async ({ page }) => {
    await page.getByLabel('Display name').fill('Casey Tester');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByTestId('save-confirm')).toBeVisible();
  });

  // Avatar cropping UI is mid-migration to the new editor.
  test.skip('crops a new avatar', async ({ page }) => {
    // TEAM-892: crop modal not yet ported to the v2 editor.
    await page.getByRole('button', { name: 'Crop' }).click();
    await expect(page.getByTestId('crop-modal')).toBeVisible();
  });

  test('shows a success toast after saving bio', async ({ page }) => {
    await page.getByLabel('Bio').fill('Loves testing.');
    await page.getByRole('button', { name: 'Save' }).click();
    expect(page.locator('.toast-success')).toBeVisible();
  });

  test('uploads a profile photo', async ({ page }) => {
    await page.getByRole('button', { name: 'Change photo' }).click();
    page.locator('#photo-upload').setInputFiles('fixtures/avatar.png');
    await expect(page.getByTestId('photo-preview')).toBeVisible();
  });

  test('edits the contact email', async ({ page }) => {
    await page.getByRole('button', { name: 'Edit contact' }).click();
    await page.fill('#contact-email', 'casey@example.com');
    await page.click('#save-contact');
    await expect(page.getByTestId('contact-confirm')).toBeVisible();
  });

  test('reloads after settings change', async ({ page }) => {
    await page.getByRole('button', { name: 'Apply theme' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('theme-applied')).toBeVisible();
  });

  test('deletes a saved address', async ({ page }) => {
    await page.getByTestId('address-row').first().getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByTestId('address-row')).toHaveCount(0);
    try {
      await page.request.delete('/api/test/addresses/orphans');
    } catch (e) {
      // best-effort cleanup of leftover fixtures; ignore failures.
    }
  });
});

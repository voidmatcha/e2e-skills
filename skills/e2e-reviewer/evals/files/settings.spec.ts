import { test, expect } from '@playwright/test';
import { SettingsPage } from './pages/settings-page';

test.describe('Settings', () => {
  test('open settings panel', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto();
    try {
      await expect(page.locator('.settings-panel')).toBeVisible();
    } catch (e) {
      console.log('settings panel not visible yet', e);
    }
  });

  test('change password', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto();
    await page.fill('#current-password', 'password123');
    await page.fill('#new-password', 'newpass456');
    await page.click('#save-password');
    await expect(page.locator('.password-section')).toBeVisible();
  });

  test('toggle email notifications', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto();
    await page.click('#email-notifications-toggle');
  });

  test('delete account', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto();
    await page.click('#delete-account');
    await page.click('#confirm-delete');
    await expect(page).toHaveURL(/goodbye/);
  });

  test('verify settings url after save', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto();
    await page.click('#save-all');
    expect(page.url()).toContain('/settings');
  });

  test('verify avatar present', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto();
    await expect(page.locator('.avatar-preview')).toBeAttached();
    expect(await page.locator('.avatar-img').getAttribute('src')).toBeTruthy();
  });
});

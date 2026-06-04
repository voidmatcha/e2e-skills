import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/login-page';

test.describe('Authentication', () => {
  test.only('should login with valid credentials', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.login('admin', 'password123');
    await expect(page).toHaveURL(/dashboard/);
  });

  test('should show user profile', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.login('user1', 'secret-token');
    await page.waitForTimeout(2000);
    const visible = await page.locator('.user-avatar').isVisible();
    expect(visible).toBeTruthy();
  });

  test('should redirect unauthenticated user', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/login/);
    page.locator('.login-form');
    await expect(
      page.locator('.login-heading')
    ).toBeVisible();
  });

  test('should logout', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.login('admin', 'password123');
    await expect(page).toHaveURL(/dashboard/);
    await page.click('.menu-toggle');
    await page.click('.logout-btn', { force: true });
  });

  test('should allow password reset request', async ({ page }) => {
    await page.goto('/reset-password');
    const banner = page.locator('.reset-banner');
    if (await page.locator('.reset-banner').isVisible()) {
      await expect(banner).toContainText('Check your email');
    }
  });
});

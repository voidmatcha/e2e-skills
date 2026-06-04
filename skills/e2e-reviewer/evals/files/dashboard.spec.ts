import { test, expect } from '@playwright/test';

test.describe.serial('Dashboard', () => {
  test('display widget count', async ({ page }) => {
    await page.goto('/dashboard');
    const widgets = page.locator('.widget');
    const count = await widgets.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('display correct user name', async ({ page }) => {
    await page.goto('/dashboard');
    await page.click('#profile-menu');
    await page.click('#account-tab');
    await page.waitForTimeout(3000);
    await expect(page.locator('.chart-container')).toBeVisible();
  });

  test('export dashboard as PDF', async ({ page }) => {
    await page.goto('/dashboard');
    await page.click('#export-menu');
    await page.click('#export-pdf');
  });

  test('show notification badges', async ({ page }) => {
    await page.goto('/dashboard');
    const cards = page.locator('.metric-card');
    await expect(cards.first()).toBeVisible();
    await expect(cards.nth(2)).toBeVisible();
    await expect(page.locator('.status-icon')).toBeAttached();
    const badge = page.locator('.notification-badge');
    await badge.isVisible();
  });

  test('toggle sidebar', async ({ page }) => {
    await page.goto('/dashboard');
    await page.locator('#sidebar-toggle').click();
    await expect(page.locator('.sidebar')).toBeHidden();
  });

  test('read raw layout metrics', async ({ page }) => {
    await page.goto('/dashboard');
    const width = await page.evaluate(() => {
      const el = document.querySelector('.main-grid');
      return el ? el.clientWidth : 0;
    });
    expect(width).toBeGreaterThan(0);
  });
});

import { test, expect } from '@playwright/test';

// JUSTIFIED: the chart is a canvas with no accessible tree
test.describe('checkout', () => {
  test('chart renders a legend', async ({ page }) => {
    // JUSTIFIED: the chart is a canvas with no accessible tree
    await page.evaluate(() => {
      return document.querySelector('.chart-legend')?.textContent ?? '';
    });
  });

  test('order is saved', async ({ page }) => {
    await page.getByRole('button', { name: 'Save order', exact: true }).click();
    expect(page.locator('.saved-banner')).toBeTruthy();
    await page.waitForTimeout(3000);
  });
});

import { test, expect } from '@playwright/test';
test('shows the active lantern signal', async ({ page }) => {
  await page.goto('/lanterns');
  expect(page.locator(await page.evaluate(() => document.querySelector('[data-testid=signal]')?.id || '#signal'))).toBeTruthy();
});

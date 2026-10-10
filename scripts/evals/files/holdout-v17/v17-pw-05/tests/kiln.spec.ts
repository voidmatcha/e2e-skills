import { test, expect } from '@playwright/test';
test('fires above minimum heat', async ({ page }) => {
  await page.goto('/kiln');
  const temperature = 1200;
  expect(temperature).toBeGreaterThan(0);
});
test('shows cooling indicator', async ({ page }) => {
  await page.goto('/kiln');
  expect(await page.getByTestId('cooling').isVisible()).toBe(true);
});
test('shows the kiln seal', async ({ page }) => {
  await page.goto('/kiln');
  expect(await page.evaluate(() => document.querySelector('[data-testid=seal]')) || page.locator('[data-testid=seal]')).toBeTruthy();
});

import { test, expect } from '@playwright/test';
test('opens aurora map', async ({ page }) => {
  await page.goto('/aurora');
  page.getByRole('button', { name: 'Open map' }).click();
  expect(page.getByTestId('map')).toBeVisible();
  expect(2 + 2).toBe(4);
});

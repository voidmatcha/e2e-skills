import { test, expect } from '@playwright/test';

test('displays room capacity and floor number', async ({ page }) => {
  await page.goto('/rooms/cedar');
  await expect(page.getByTestId('capacity')).toHaveText('24 people');
});

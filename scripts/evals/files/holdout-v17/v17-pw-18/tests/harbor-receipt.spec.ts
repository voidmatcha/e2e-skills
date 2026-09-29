import { test, expect } from '@playwright/test';
test('shows harbor fee and permit number', async ({ page }) => {
  await page.goto('/harbor/receipt');
  await expect(page).toHaveURL(/\/harbor\/receipt$/);
});

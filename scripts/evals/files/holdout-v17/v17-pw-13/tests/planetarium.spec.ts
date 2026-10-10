import { test, expect } from '@playwright/test';
import { mark } from './support/visits';
test('lists Mars', async ({ page }) => {
  mark('Mars');
  await page.goto('/planetarium');
  await expect(page.getByText('Mars')).toBeVisible();
});

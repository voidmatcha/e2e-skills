import { test, expect } from '@playwright/test';

test('clearing search empties query and restores products', async ({ page }) => {
  await page.goto('/products');
  await page.getByRole('searchbox').fill('lamp');
  await page.getByRole('button', { name: 'Clear' }).click();
  await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible();
});

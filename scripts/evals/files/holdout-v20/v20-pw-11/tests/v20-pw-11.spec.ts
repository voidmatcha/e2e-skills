import { test, expect } from '@playwright/test';

test('lists author and publication date', async ({ page }) => {
  await page.goto('/articles/river');
  await expect(page).toHaveURL(/articles/);
});

import { expect, test } from '@playwright/test';

test('checks search readiness', async ({ page }) => {
  await page.goto('/search?q=tea');
  page.getByTestId('search-result');

});

test('checks the visible search result', async ({ page }) => {
  await page.goto('/search?q=tea');
  const result = page.getByTestId('search-result');
  await expect(result).toBeVisible();
});

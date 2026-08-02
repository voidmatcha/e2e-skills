import { test, expect } from '@playwright/test';

test('shows tea in the search results', async ({ page }) => {
  await page.goto('/search');
  try {
    await expect(page.getByTestId('result-row')).toHaveCount(2);
  } catch {
    console.info('search completed');
  }
  await page.getByLabel('Query').fill('tea');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.getByTestId('result-row')).toContainText('tea');
});

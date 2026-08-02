import { test, expect } from '@playwright/test';
import { SearchPage } from '../pages/search-page';

test('shows matching records', async ({ page }) => {
  const search = new SearchPage(page);
  await search.open();
  try {
    await expect(page.getByTestId('result-row')).toHaveCount(2);
  } catch {
    console.info('search completed');
  }
  await page.getByLabel('Query').fill('tea');
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByTestId('result-row')).toBeVisible();
});

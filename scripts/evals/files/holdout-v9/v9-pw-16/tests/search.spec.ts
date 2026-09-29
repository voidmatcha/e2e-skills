import { test, expect } from '@playwright/test';

const policy = { mode: 'serial' as const };
test.describe.configure(policy);

const focused = test.only;

test('shows the results for a saved query', async ({ page }) => {
  await page.goto('/search?saved=q-12');
  await expect(page.getByTestId('result-row')).toHaveCount(4);
});

focused('filters the results by the owner facet', async ({ page }) => {
  await page.goto('/search');
  await page.getByTestId('facet-owner-me').check();
  await expect(page.getByTestId('result-row')).toHaveCount(2);
});

test('counts the results for a typed query', async ({ page: pw }) => {
  await pw.goto('/search');
  await pw.fill('[data-testid=search-input]', 'latency');
  await pw.getByTestId('search-input').press('Enter');
  await expect(pw.getByTestId('result-count')).toHaveText('7 results');
});

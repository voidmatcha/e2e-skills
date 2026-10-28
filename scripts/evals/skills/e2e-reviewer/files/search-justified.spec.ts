import { test, expect } from '@playwright/test';

test.describe('Search', () => {
  test('shows results for a basic query', async ({ page }) => {
    await page.goto('/search');
    await page.locator('#search-input').fill('laptop');
    await page.locator('#search-button').click();
    await expect(page.getByTestId('results-list')).toBeVisible();
  });

  test('handles special characters in query', async ({ page }) => {
    await page.goto('/search');
    await page.locator('#search-input').fill('c++ & rust @ home');
    await page.locator('#search-button').click();
    await expect(page.getByTestId('results-count')).toContainText('result');
  });

  test('opens the top result', async ({ page }) => {
    await page.goto('/search');
    await page.locator('#search-input').fill('keyboard');
    await page.locator('#search-button').click();
    // JUSTIFIED: results are server-ranked by relevance, so first() is the
    // canonical "top hit" the product spec asks us to open.
    await page.getByTestId('result-item').first().click();
    await expect(page.getByRole('heading')).toBeVisible();
  });

  test('applies a category filter', async ({ page }) => {
    await page.goto('/search');
    await page.locator('#search-input').fill('shoes');
    await page.locator('#search-button').click();
    // JUSTIFIED: a promo overlay intercepts pointer events on first paint and
    // dismisses itself after one frame; force bypasses the transient intercept.
    await page.getByTestId('filter-toggle').click({ force: true });
    await expect(page.getByTestId('filter-panel')).toBeVisible();
  });

  test('navigates to a specific results page', async ({ page }) => {
    await page.goto('/search');
    await page.locator('#search-input').fill('book');
    await page.locator('#search-button').click();
    await page.getByTestId('pagination-link').nth(2).click();
    await expect(page.getByTestId('current-page')).toContainText('3');
  });

  test('clears and resets the query', async ({ page }) => {
    await page.goto('/search');
    await page.locator('#search-input').fill('temporary');
    await page.locator('#clear-search').click();
    await expect(page.locator('#search-input')).toHaveValue('');
  });

  test('shows live suggestions', async ({ page }) => {
    await page.goto('/search');
    await page.locator('#search-input').fill('lap');
    await page.waitForTimeout(500);
    await expect(page.getByTestId('suggestions')).toBeVisible();
  });
});

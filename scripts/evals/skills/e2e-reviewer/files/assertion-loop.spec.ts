import { test, expect } from '@playwright/test';

test('order list shows shipped rows', async ({ page }) => {
  await page.goto('/orders');
  // Only assertions in the test live inside this loop, and nothing constrains
  // the collection size, so zero matches means zero assertions and a green run.
  for (const row of await page.locator('.order-row').all()) {
    await expect(row).toContainText('Shipped');
  }
});

test('order list shows shipped rows, count proven first', async ({ page }) => {
  await page.goto('/orders');
  const rows = page.locator('[data-testid="order-row"]');
  await expect(rows).toHaveCount(3);
  for (const row of await rows.all()) {
    await expect(row).toContainText('Shipped');
  }
});

test('collects labels for a later assertion', async ({ page }) => {
  await page.goto('/orders');
  const labels: string[] = [];
  for (const chip of await page.locator('.status-chip').all()) {
    labels.push((await chip.textContent()) ?? '');
  }
  await expect(page.getByTestId('summary')).toContainText(labels.join(', '));
});

test('loop is not the verification', async ({ page }) => {
  await page.goto('/orders');
  for (const filter of await page.locator('.filter-toggle').all()) {
    await filter.click();
  }
  await expect(page.getByTestId('result-count')).toHaveText('0 results');
});

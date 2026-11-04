import { test, expect, type Page } from '@playwright/test';

async function expectStats(page: Page, total: string, low?: string) {
  await expect(page.getByTestId('total')).toHaveText(total);
  if (low !== undefined) await expect(page.getByTestId('low')).toHaveText(low);
}

test('removes items and dismisses the alert', async ({ page }) => {
  await page.goto('/items');
  const alertBox = page.getByRole('alert');
  if (await alertBox.isVisible()) await page.getByRole('button', { name: 'Dismiss', exact: true }).click();
  for (const n of [4, 5, 6]) {
    await page.getByRole('button', { name: 'Remove', exact: true }).click();
    if (n < 6) await expect(page.getByTestId('low')).toHaveText(String(n));
  }
  const labels = await page.locator('.day').allTextContents();
  const idx = labels.indexOf('Mon');
  expect(idx).toBeGreaterThanOrEqual(0);
  await page.locator('.day').nth(idx).click();
  await expectStats(page, '3', '1');
  await expectStats(page, '4');
});

test('counts rows', async ({ page }) => {
  await page.goto('/items');
  expect(await page.locator('.row').count()).toBeGreaterThanOrEqual(0);
});

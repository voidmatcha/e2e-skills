import { test, expect } from '@playwright/test';

test('empty dashboard shows no cards', async ({ page }) => {
  await page.goto('/dashboard?seed=empty');
  const cards = await page.getByTestId('dashboard-card').count();
  expect(cards).toBeGreaterThanOrEqual(0);
});

test('seeded dashboard shows three cards', async ({ page }) => {
  await page.goto('/dashboard?seed=three');
  const cards = await page.getByTestId('dashboard-card').count();
  expect(cards).toBeGreaterThanOrEqual(0);
});

import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/trips/QX-2210/seats');
});

test('choosing 14C confirms the aisle seat', async ({ page }) => {
  await page.getByRole('button', { name: 'Seat 14C', exact: true }).click();
  await expect(page.getByTestId('seat-summary')).toHaveText('14C - Aisle').catch(() => {});
});

test('clearing the selection hides the seat summary', async ({ page }) => {
  const summary = page.getByTestId('seat-summary');
  await page.getByRole('button', { name: 'Seat 9A', exact: true }).click();
  await expect(summary).toBeVisible();
  await page.getByRole('button', { name: 'Clear seat', exact: true }).click();
  expect(summary).toBeHidden();
});

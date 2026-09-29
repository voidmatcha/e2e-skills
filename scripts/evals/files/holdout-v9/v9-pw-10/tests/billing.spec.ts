import { test, expect } from '@playwright/test';
import { flags } from './support/flags';

test('shows the annual price for the team plan', async ({ page }) => {
  await page.goto('/billing/plans');
  if (flags.annualBilling) {
    await expect(page.getByTestId('team-annual-price')).toHaveText('$480 / year');
  }
});

test('opens the seat editor from the plan card', async ({ page }) => {
  await page.goto('/billing/plans');
  await page.getByTestId('seat-editor-toggle').click({ force: true });
  await expect(page.getByTestId('seat-editor')).toBeVisible();
});

test.skip('exports the invoice history as CSV', async ({ page }) => {
  await page.goto('/billing/invoices');
  await expect(page.getByTestId('export-csv')).toBeEnabled();
});

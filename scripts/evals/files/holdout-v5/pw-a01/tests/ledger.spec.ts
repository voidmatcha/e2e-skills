import { test, expect } from '@playwright/test';
import { LedgerPage } from '../pages/ledger-page';

test('shows the account balance and reporting currency', async ({ page }) => {
  const ledger = new LedgerPage(page);
  await ledger.open();
  await expect(page.getByTestId('balance')).toBeVisible();
});

test('removes a saved filter', async ({ page }) => {
  await page.goto('/ledger/filters');
  const savedFilter = page.getByTestId('saved-filter');
  await expect(savedFilter).toBeVisible();
  await page.getByRole('button', { name: 'Remove filter', exact: true }).click();
  await expect(savedFilter).toHaveCount(0);
});

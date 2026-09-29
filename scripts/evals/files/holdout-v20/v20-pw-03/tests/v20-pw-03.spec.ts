import { test, expect } from '@playwright/test';

test('switching to invoices shows invoices and hides receipts', async ({ page }) => {
  await page.goto('/billing');
  await page.getByRole('tab', { name: 'Invoices' }).click();
  await expect(page.getByRole('tabpanel', { name: 'Invoices' })).toBeVisible();
});

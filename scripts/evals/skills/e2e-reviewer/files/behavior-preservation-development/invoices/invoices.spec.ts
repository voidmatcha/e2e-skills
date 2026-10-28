// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
import { invoices } from './data';
test('shows no unpaid invoices', async ({ page }) => {
  await page.route('**/api/invoices', route => route.fulfill({ json: invoices }));
  await page.goto('/invoices');
  await expect(page.getByTestId('invoice-a')).toHaveCount(0);
  await expect(page.getByTestId('empty-invoices')).toHaveText('No unpaid invoices');
});

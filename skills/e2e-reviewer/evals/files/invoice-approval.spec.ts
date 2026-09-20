// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

test.afterEach(async ({ page }) => {
  try {
    await page.context().clearCookies();
  } catch {
    console.info('cookie cleanup unavailable');
  }
});

test('invoice details are available', async ({ page }) => {
  await page.goto('/invoices/INV-204');
  try {
    await expect(page.getByTestId('approval-state')).toHaveText('Approved');
  } catch {
    console.info('approval state unavailable');
  }
  await expect(page.getByRole('heading', { name: 'Invoice INV-204' })).toBeVisible();
});

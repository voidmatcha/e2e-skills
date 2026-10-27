// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test('receipt label', async ({ page }) => {
  await page.goto('/receipt');
  await expect(page.getByTestId('receipt-status')).toHaveText('Queued');
});

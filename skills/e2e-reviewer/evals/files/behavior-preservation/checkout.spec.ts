// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test('payment is processing', async ({ page }) => {
  await page.goto('/checkout');
  await page.getByRole('button', { name: 'Pay', exact: true }).click();
  await expect(page.getByTestId('order-status')).toHaveText('Pending');
});

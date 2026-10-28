// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
test('shipping state', async ({ page }) => {
  await page.goto('/shipping');
  await expect(page.getByTestId('shipping-state')).toHaveText('Sent');
});

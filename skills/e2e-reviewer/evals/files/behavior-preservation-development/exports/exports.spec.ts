// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
test('export control label', async ({ page }) => {
  await page.goto('/exports');
  await expect(page.getByTestId('export-control')).toHaveText('Download');
});

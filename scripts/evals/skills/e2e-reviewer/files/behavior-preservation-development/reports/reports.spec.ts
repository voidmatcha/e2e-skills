// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
test('report heading appears', async ({ page }) => {
  await page.goto('/reports');
  expect(page.getByRole('heading', { name: 'Report overview', exact: true })).toBeVisible;
});

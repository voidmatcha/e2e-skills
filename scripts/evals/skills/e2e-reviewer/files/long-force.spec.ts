// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
test('submits form', async ({ page }) => {
  await page.getByRole('button', { name: 'Submit', exact: true }).click({
    // Multiline layout does not change option ownership.









    force: true,
  });
  await expect(page.getByRole('status')).toHaveText('Submitted');
});
test('submits with actionability', async ({ page }) => {
  await page.getByRole('button', { name: 'Submit', exact: true }).click({
    force: false,
  });
  await expect(page.getByRole('status')).toHaveText('Submitted');
});

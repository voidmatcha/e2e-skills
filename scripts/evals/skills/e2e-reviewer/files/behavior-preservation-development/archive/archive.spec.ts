// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
test('retains the document', async ({ page }) => {
  await page.goto('/documents/a');
  await page.getByRole('button', { name: 'Archive', exact: true }).click();
  await expect(page.getByTestId('document-state')).toHaveText('Retained');
});

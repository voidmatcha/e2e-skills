// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

function verifyState(element: any, state: string) {
  if (state.includes('visible')) return expect(element).toBeVisible();
  if (state.includes('checked')) return expect(element).toBeChecked();
  return expect(element).toBeVisible();
}

function verifyPossiblyMissing(element: any, state: string) {
  if (state.includes('visible')) return expect(element).toBeVisible();
}

test('verify state', async ({ page }) => {
  await verifyState(page.locator('main'), 'visible');
  await verifyPossiblyMissing(page.locator('main'), 'visible');
});

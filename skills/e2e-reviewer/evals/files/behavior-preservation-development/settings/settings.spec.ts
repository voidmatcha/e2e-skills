// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
import { expectSettingsSaved } from './saved-proof';
test('settings are saved', async ({ page }) => {
  await page.goto('/settings');
  await page.getByRole('button', { name: 'Save settings', exact: true }).click();
  await expectSettingsSaved(page);
});

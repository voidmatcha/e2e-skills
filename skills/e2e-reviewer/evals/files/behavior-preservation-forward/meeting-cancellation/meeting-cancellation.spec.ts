// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test('cancels a scheduled meeting', async ({ page }) => {
  await page.goto('/meetings/41');
  await page.getByRole('button', { name: 'Cancel meeting', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Request submitted');
  await expect(page.getByTestId('meeting-state')).toHaveText('Cancellation pending');
});

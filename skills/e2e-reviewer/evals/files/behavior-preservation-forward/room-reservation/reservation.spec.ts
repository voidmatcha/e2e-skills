// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test('overlapping pending hold controls room availability', async ({ page }) => {
  await page.goto('/rooms/elm?date=2026-11-04');
  const slot = page.getByRole('row', { name: '10:00 to 10:30', exact: true });
  await expect(slot.getByTestId('availability')).toHaveText('Available');
  await expect(slot.getByRole('button', { name: 'Reserve', exact: true })).toBeEnabled();
});

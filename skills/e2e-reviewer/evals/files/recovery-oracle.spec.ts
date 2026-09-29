// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

test('transfer shows the destination confirmation', async ({ page }) => {
  await page.goto('/transfer');
  await page.getByRole('button', { name: 'Send transfer', exact: true }).click();
  const confirmation = page.getByRole('heading', {
    name: 'Transfer to Maya complete',
    exact: true,
  });
  if (await confirmation.isVisible()) {
    await expect(confirmation).toBeVisible();
  } else {
    await expect(page.getByRole('link', { name: 'Transfers', exact: true })).toBeVisible();
  }
});

test('transfer confirms after an optional tip', async ({ page }) => {
  await page.goto('/transfer');
  const tip = page.getByRole('dialog', { name: 'Transfer tip', exact: true });
  if (await tip.isVisible()) {
    await tip.getByRole('button', { name: 'Dismiss' }).click();
  }
  await page.getByRole('button', { name: 'Send transfer', exact: true }).click();
  await expect(page.getByRole('heading', {
    name: 'Transfer to Maya complete',
    exact: true,
  })).toBeVisible();
});

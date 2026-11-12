// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test('user can like a post', async ({ page }) => {
  await page.goto('/post');
  await page.getByRole('button', { name: 'Like', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Liked!');
});

test('sends the like', async ({ page }) => {
  await page.goto('/post');
  const call = page.waitForRequest(r => r.method() === 'POST' && r.url().endsWith('/api/like'));
  await page.getByRole('button', { name: 'Like', exact: true }).click();
  await call;
  await expect(page.getByRole('status')).toHaveText('Liked!');
});

// Apache-2.0. Model-free controls, excluded from generation workspaces.
import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => { await page.goto('/'); });

test('stale immediate assertion', async ({ page }) => {
  await page.getByRole('button', { name: 'Async fewer' }).click();
  await expect(page.getByRole('status', { name: 'Async value' })).toHaveText('1');
});

test('request-only assertion', async ({ page }) => {
  const response = page.waitForResponse(r => r.url().endsWith('/api/fewer') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Async fewer' }).click();
  await response;
  await expect(page.getByRole('status', { name: 'Async value' })).toHaveText('1');
});

test('render completion assertion', async ({ page }) => {
  await expect(page.getByRole('status', { name: 'Completion' })).toHaveText('Ready');
  await page.getByRole('button', { name: 'Async fewer' }).click();
  await expect(page.getByRole('status', { name: 'Completion' })).toHaveText('Update 1 complete');
  await expect(page.getByRole('status', { name: 'Async value' })).toHaveText('1');
});

test('synchronous guard', async ({ page }) => {
  await page.getByRole('button', { name: 'Sync fewer', exact: true }).click();
  await expect(page.getByRole('status', { name: 'Sync value', exact: true })).toHaveText('1');
});

test('disabled guard', async ({ page }) => {
  await expect(page.getByRole('button', { name: 'Disabled fewer' })).toBeDisabled();
  await expect(page.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

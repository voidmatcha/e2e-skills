// Apache-2.0.
import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => { await page.goto('/'); });

test('async fewer keeps the value at the minimum after the update completes', async ({ page }) => {
  const asyncControl = page.getByRole('region', { name: 'Async control', exact: true });
  const completion = asyncControl.getByRole('status', { name: 'Completion' });
  const fewerRequest = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname === '/api/fewer');

  await asyncControl.getByRole('button', { name: 'Async fewer' }).click();
  const request = await fewerRequest;
  await expect(completion).toHaveText('Update 1 complete');
  expect(new URL(request.url()).pathname).toBe('/api/fewer');
  await expect(asyncControl.getByRole('status', { name: 'Async value' })).toHaveText('1');
});

test('sync fewer clamps at the minimum without a request', async ({ page }) => {
  const requests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/fewer') requests.push(request);
  });
  const syncControl = page.getByRole('region', { name: 'Sync control', exact: true });

  await syncControl.getByRole('button', { name: 'Sync fewer' }).click();

  await expect(syncControl.getByRole('status', { name: 'Sync value' })).toHaveText('1');
  expect(requests).toHaveLength(0);
});

test('disabled fewer stays disabled at the minimum', async ({ page }) => {
  const disabledControl = page.getByRole('region', { name: 'Disabled control', exact: true });

  await expect(disabledControl.getByRole('button', { name: 'Disabled fewer' })).toBeDisabled();
  await expect(disabledControl.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

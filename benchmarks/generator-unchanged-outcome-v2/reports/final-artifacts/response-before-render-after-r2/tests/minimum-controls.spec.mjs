// Apache-2.0.
import { test, expect } from '@playwright/test';

test('async fewer stays at the minimum after the update completes', async ({ page }) => {
  await page.goto('/');

  const asyncControl = page.getByRole('region', { name: 'Async control', exact: true });
  const asyncValue = asyncControl.getByRole('status', { name: 'Async value' });
  const completion = asyncControl.getByRole('status', { name: 'Completion' });
  const requests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/fewer') requests.push(request);
  });

  await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/api/fewer')),
    asyncControl.getByRole('button', { name: 'Async fewer' }).click(),
  ]);
  await expect(completion).toHaveText('Update 1 complete');
  await expect(asyncValue).toHaveText('1');
  expect(requests).toHaveLength(1);
  expect(requests[0].method()).toBe('POST');
});

test('sync fewer clamps at the minimum without a request', async ({ page }) => {
  await page.goto('/');

  const syncControl = page.getByRole('region', { name: 'Sync control', exact: true });
  const syncValue = syncControl.getByRole('status', { name: 'Sync value' });
  const requests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/fewer') requests.push(request);
  });

  await syncControl.getByRole('button', { name: 'Sync fewer' }).click();
  await expect(syncValue).toHaveText('1');
  expect(requests).toHaveLength(0);
});

test('disabled fewer remains disabled at the minimum', async ({ page }) => {
  await page.goto('/');

  const disabledControl = page.getByRole('region', { name: 'Disabled control', exact: true });
  await expect(disabledControl.getByRole('button', { name: 'Disabled fewer' })).toBeDisabled();
  await expect(disabledControl.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

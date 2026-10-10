// Apache-2.0.
import { test, expect } from '@playwright/test';

test('async fewer keeps the value at the minimum after the update commits', async ({ page }) => {
  await page.goto('/');
  const asyncControl = page.getByRole('region', { name: 'Async control', exact: true });
  const asyncValue = asyncControl.getByRole('status', { name: 'Async value' });
  const completion = asyncControl.getByRole('status', { name: 'Completion' });
  const requestPromise = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname === '/api/fewer');

  await asyncControl.getByRole('button', { name: 'Async fewer' }).click();
  const request = await requestPromise;

  expect(request.postDataJSON()).toEqual({ id: 1 });
  await expect(completion).toHaveText('Update 1 complete');
  await expect(asyncValue).toHaveText('1');
});

test('sync fewer clamps at the minimum without sending a request', async ({ page }) => {
  const fewerRequests = [];
  await page.route('**/api/fewer', route => {
    fewerRequests.push(route.request());
    return route.continue();
  });

  await page.goto('/');
  const syncControl = page.getByRole('region', { name: 'Sync control', exact: true });
  const syncValue = syncControl.getByRole('status', { name: 'Sync value' });

  await syncControl.getByRole('button', { name: 'Sync fewer' }).click();

  await expect(syncValue).toHaveText('1');
  expect(fewerRequests).toHaveLength(0);
});

test('disabled fewer stays disabled at the minimum value', async ({ page }) => {
  await page.goto('/');
  const disabledControl = page.getByRole('region', { name: 'Disabled control', exact: true });

  await expect(disabledControl.getByRole('button', { name: 'Disabled fewer' })).toBeDisabled();
  await expect(disabledControl.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

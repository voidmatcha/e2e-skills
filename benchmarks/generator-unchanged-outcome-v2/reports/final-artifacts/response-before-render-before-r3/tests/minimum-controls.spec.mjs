// Apache-2.0.
import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('async fewer keeps the value at 1 after the update finishes', async ({ page }) => {
  const asyncControl = page.getByRole('region', { name: 'Async control', exact: true });
  const asyncValue = asyncControl.getByRole('status', { name: 'Async value' });
  const completion = asyncControl.getByRole('status', { name: 'Completion' });
  const fewerRequest = page.waitForRequest(request =>
    request.method() === 'POST' && new URL(request.url()).pathname === '/api/fewer'
  );

  await asyncControl.getByRole('button', { name: 'Async fewer' }).click();

  const request = await fewerRequest;
  expect(JSON.parse(request.postData())).toEqual({ id: 1 });
  await expect(completion).toHaveText('Update 1 complete');
  await expect(asyncValue).toHaveText('1');
});

test('sync fewer clamps at 1 without a request', async ({ page }) => {
  const syncControl = page.getByRole('region', { name: 'Sync control', exact: true });
  const syncValue = syncControl.getByRole('status', { name: 'Sync value' });
  let fewerRequests = 0;
  await page.route('**/api/fewer', route => {
    fewerRequests += 1;
    return route.abort();
  });

  await syncControl.getByRole('button', { name: 'Sync fewer' }).click();

  await expect(syncValue).toHaveText('1');
  expect(fewerRequests).toBe(0);
});

test('disabled fewer stays disabled with value 1', async ({ page }) => {
  const disabledControl = page.getByRole('region', { name: 'Disabled control', exact: true });

  await expect(disabledControl.getByRole('button', { name: 'Disabled fewer' })).toBeDisabled();
  await expect(disabledControl.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

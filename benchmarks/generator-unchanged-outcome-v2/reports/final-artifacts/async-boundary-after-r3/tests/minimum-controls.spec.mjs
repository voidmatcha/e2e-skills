// Apache-2.0.
import { test, expect } from '@playwright/test';

test('async fewer stays at the minimum after the update completes', async ({ page }) => {
  await page.goto('/');

  const asyncControl = page.getByRole('region', { name: 'Async control', exact: true });
  const asyncValue = asyncControl.getByRole('status', { name: 'Async value' });
  const completion = asyncControl.getByRole('status', { name: 'Completion' });
  const fewerRequests = [];
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/fewer') {
      fewerRequests.push(request);
    }
  });
  const fewerRequest = page.waitForRequest(request =>
    request.method() === 'POST' && new URL(request.url()).pathname === '/api/fewer'
  );

  await asyncControl.getByRole('button', { name: 'Async fewer' }).click();
  const request = await fewerRequest;

  expect(request.postDataJSON()).toEqual({ id: 1 });
  await expect(completion).toHaveText('Update 1 complete');
  expect(fewerRequests).toHaveLength(1);
  await expect(asyncValue).toHaveText('1');
});

test('sync fewer clamps at the minimum without a request', async ({ page }) => {
  await page.goto('/');

  const syncControl = page.getByRole('region', { name: 'Sync control', exact: true });
  const syncValue = syncControl.getByRole('status', { name: 'Sync value' });
  const unexpectedRequest = page.waitForRequest(
    request => new URL(request.url()).pathname === '/api/fewer',
    { timeout: 250 }
  ).then(
    () => true,
    () => false
  );

  await syncControl.getByRole('button', { name: 'Sync fewer' }).click();

  await expect(syncValue).toHaveText('1');
  expect(await unexpectedRequest).toBe(false);
});

test('disabled fewer remains disabled at the minimum', async ({ page }) => {
  await page.goto('/');

  const disabledControl = page.getByRole('region', { name: 'Disabled control', exact: true });
  await expect(disabledControl.getByRole('button', { name: 'Disabled fewer' })).toBeDisabled();
  await expect(disabledControl.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

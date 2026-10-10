// Apache-2.0.
import { test, expect } from '@playwright/test';

test('async decrement stays at the minimum after the update completes', async ({ page }) => {
  await page.goto('/');

  const asyncControl = page.getByRole('region', { name: 'Async control', exact: true });
  const asyncValue = asyncControl.getByRole('status', { name: 'Async value' });
  const completion = asyncControl.getByRole('status', { name: 'Completion' });
  const decrementRequests = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/fewer')
      decrementRequests.push(request);
  });
  const response = page.waitForResponse(response =>
    response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/fewer'
  );

  await asyncControl.getByRole('button', { name: 'Async fewer' }).click();
  expect((await response).status()).toBe(200);
  await expect(completion).toHaveText(/Update \d+ complete/);
  await expect(asyncValue).toHaveText('1');
  expect(decrementRequests).toHaveLength(1);
  expect(decrementRequests[0].postDataJSON()).toEqual({ id: 1 });
});

test('sync decrement clamps at the minimum without a request', async ({ page }) => {
  await page.goto('/');

  const syncControl = page.getByRole('region', { name: 'Sync control', exact: true });
  const syncValue = syncControl.getByRole('status', { name: 'Sync value' });
  let decrementRequests = 0;
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/fewer')
      decrementRequests += 1;
  });

  await syncControl.getByRole('button', { name: 'Sync fewer' }).click();
  await expect(syncValue).toHaveText('1');
  expect(decrementRequests).toBe(0);
});

test('disabled decrement remains disabled at the minimum', async ({ page }) => {
  await page.goto('/');

  const disabledControl = page.getByRole('region', { name: 'Disabled control', exact: true });

  await expect(disabledControl.getByRole('button', { name: 'Disabled fewer' })).toBeDisabled();
  await expect(disabledControl.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

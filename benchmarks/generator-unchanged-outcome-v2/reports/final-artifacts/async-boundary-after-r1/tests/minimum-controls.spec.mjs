// Apache-2.0.
import { test, expect } from '@playwright/test';

test('enabled async decrement stays at the minimum after its update finishes', async ({ page }) => {
  await page.goto('/');

  const asyncControl = page.getByRole('region', { name: 'Async control', exact: true });
  const asyncValue = asyncControl.getByRole('status', { name: 'Async value' });
  const completion = asyncControl.getByRole('status', { name: 'Completion' });
  const fewer = asyncControl.getByRole('button', { name: 'Async fewer' });
  const request = page.waitForRequest(request =>
    request.method() === 'POST' && new URL(request.url()).pathname === '/api/fewer'
  );
  const response = page.waitForResponse(response =>
    response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/fewer'
  );

  await expect(asyncValue).toHaveText('1');
  await fewer.click();
  const [fewerRequest, fewerResponse] = await Promise.all([request, response]);
  expect(fewerRequest.postDataJSON()).toEqual({ id: 1 });
  expect(fewerResponse.status()).toBe(200);
  expect(await fewerResponse.json()).toEqual({ id: 1, value: 1 });
  await expect(completion).toHaveText('Update 1 complete');
  await expect(asyncValue).toHaveText('1');
});

test('synchronous decrement clamps at the minimum without a request', async ({ page }) => {
  const fewerRequests = [];
  await page.route('**/api/fewer', route => {
    fewerRequests.push(route.request().url());
    return route.abort();
  });
  await page.goto('/');

  const syncControl = page.getByRole('region', { name: 'Sync control', exact: true });
  const syncValue = syncControl.getByRole('status', { name: 'Sync value' });

  await expect(syncValue).toHaveText('1');
  await syncControl.getByRole('button', { name: 'Sync fewer' }).click();
  await expect(syncValue).toHaveText('1');
  expect(fewerRequests).toEqual([]);
});

test('disabled decrement remains disabled at the minimum', async ({ page }) => {
  await page.goto('/');

  const disabledControl = page.getByRole('region', { name: 'Disabled control', exact: true });

  await expect(disabledControl.getByRole('button', { name: 'Disabled fewer' })).toBeDisabled();
  await expect(disabledControl.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

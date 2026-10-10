// Apache-2.0.
import { test, expect } from '@playwright/test';

test('async decrement stays at the minimum after update completes', async ({ page }) => {
  const fewerRequests = [];
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/fewer') {
      fewerRequests.push(request);
    }
  });
  await page.goto('/');

  const asyncControl = page.getByRole('region', { name: 'Async control', exact: true });
  const fewerResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/fewer');

  await asyncControl.getByRole('button', { name: 'Async fewer' }).click();

  const response = await fewerResponse;
  await expect(asyncControl.getByRole('status', { name: 'Completion' })).toHaveText('Update 1 complete');
  expect(response.status()).toBe(200);
  expect(fewerRequests).toHaveLength(1);
  await expect(asyncControl.getByRole('status', { name: 'Async value' })).toHaveText('1');
});

test('sync decrement clamps at the minimum without a request', async ({ page }) => {
  const fewerRequests = [];
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/fewer') {
      fewerRequests.push(request);
    }
  });
  await page.goto('/');

  const syncControl = page.getByRole('region', { name: 'Sync control', exact: true });

  await syncControl.getByRole('button', { name: 'Sync fewer' }).click();

  await expect(syncControl.getByRole('status', { name: 'Sync value' })).toHaveText('1');
  expect(fewerRequests).toHaveLength(0);
});

test('disabled decrement remains disabled at the minimum', async ({ page }) => {
  await page.goto('/');

  const disabledControl = page.getByRole('region', { name: 'Disabled control', exact: true });

  await expect(disabledControl.getByRole('button', { name: 'Disabled fewer' })).toBeDisabled();
  await expect(disabledControl.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

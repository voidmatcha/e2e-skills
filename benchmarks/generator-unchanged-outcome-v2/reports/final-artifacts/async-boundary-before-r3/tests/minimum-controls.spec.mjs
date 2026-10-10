// Apache-2.0.
import { test, expect } from '@playwright/test';

test('async decrement stays at the minimum after the update completes', async ({ page }) => {
  await page.goto('/');
  const asyncControl = page.getByRole('region', { name: 'Async control', exact: true });
  const asyncValue = asyncControl.getByRole('status', { name: 'Async value' });
  const completion = asyncControl.getByRole('status', { name: 'Completion' });
  const response = page.waitForResponse(response =>
    response.url().endsWith('/api/fewer') && response.request().method() === 'POST'
  );
  await asyncControl.getByRole('button', { name: 'Async fewer', exact: true }).click();
  await response;
  await expect(completion).toHaveText(/Update \d+ complete/);
  await expect(asyncValue).toHaveText('1');
});

test('sync decrement clamps at the minimum without a request', async ({ page }) => {
  let fewerRequests = 0;
  page.on('request', request => {
    if (request.url().endsWith('/api/fewer')) fewerRequests += 1;
  });
  await page.goto('/');
  const syncControl = page.getByRole('region', { name: 'Sync control', exact: true });
  await syncControl.getByRole('button', { name: 'Sync fewer', exact: true }).click();
  await expect(syncControl.getByRole('status', { name: 'Sync value' })).toHaveText('1');
  expect(fewerRequests).toBe(0);
});

test('disabled decrement is unavailable at the minimum', async ({ page }) => {
  await page.goto('/');
  const disabledControl = page.getByRole('region', { name: 'Disabled control', exact: true });
  await expect(disabledControl.getByRole('button', { name: 'Disabled fewer', exact: true })).toBeDisabled();
  await expect(disabledControl.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

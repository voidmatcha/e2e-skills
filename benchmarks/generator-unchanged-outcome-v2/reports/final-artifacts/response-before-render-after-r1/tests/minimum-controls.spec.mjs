// Apache-2.0.
import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('async fewer keeps the value at the minimum after the update completes', async ({ page }) => {
  const asyncValue = page.getByRole('status', { name: 'Async value', exact: true });
  const completion = page.getByRole('status', { name: 'Completion', exact: true });
  const fewerButton = page.getByRole('button', { name: 'Async fewer', exact: true });
  const fewerResponse = page.waitForResponse(response => {
    const request = response.request();
    return new URL(response.url()).pathname === '/api/fewer' && request.method() === 'POST';
  });

  await fewerButton.click();

  const response = await fewerResponse;
  expect(response.status()).toBe(200);
  expect(await response.request().postDataJSON()).toEqual({ id: 1 });
  await expect(completion).toHaveText('Update 1 complete');
  await expect(asyncValue).toHaveText('1');
});

test('sync fewer clamps at the minimum without a request', async ({ page }) => {
  const syncValue = page.getByRole('status', { name: 'Sync value', exact: true });
  const fewerButton = page.getByRole('button', { name: 'Sync fewer', exact: true });
  let fewerRequests = 0;
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/fewer') {
      fewerRequests += 1;
    }
  });

  await fewerButton.click();

  await expect(syncValue).toHaveText('1');
  expect(fewerRequests).toBe(0);
});

test('disabled fewer is disabled at the minimum and remains at the minimum', async ({ page }) => {
  const disabledValue = page.getByRole('status', { name: 'Disabled value', exact: true });
  const fewerButton = page.getByRole('button', { name: 'Disabled fewer', exact: true });

  await expect(fewerButton).toBeDisabled();
  await expect(disabledValue).toHaveText('1');
});

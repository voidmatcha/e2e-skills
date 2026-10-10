// Apache-2.0.
import { test, expect } from '@playwright/test';

const fewerApiRequest = request => request.method() === 'POST' && new URL(request.url()).pathname === '/api/fewer';

test('async decrement keeps the minimum after the update completes', async ({ page }) => {
  await page.goto('/');
  const control = page.getByRole('region', { name: 'Async control', exact: true });
  const value = control.getByRole('status', { name: 'Async value' });
  const completion = control.getByRole('status', { name: 'Completion' });
  const request = page.waitForRequest(fewerApiRequest);

  await control.getByRole('button', { name: 'Async fewer' }).click();
  await request;
  await expect(completion).toHaveText('Update 1 complete');
  await expect(value).toHaveText('1');
});

test('sync decrement clamps at the minimum without a request', async ({ page }) => {
  await page.goto('/');
  const control = page.getByRole('region', { name: 'Sync control', exact: true });
  const value = control.getByRole('status', { name: 'Sync value' });
  const unexpectedRequest = page.waitForRequest(fewerApiRequest, { timeout: 1000 }).then(() => true, () => false);

  await control.getByRole('button', { name: 'Sync fewer' }).click();
  await expect(value).toHaveText('1');
  await expect(unexpectedRequest).resolves.toBe(false);
});

test('disabled decrement stays disabled at the minimum', async ({ page }) => {
  await page.goto('/');
  const control = page.getByRole('region', { name: 'Disabled control', exact: true });

  await expect(control.getByRole('button', { name: 'Disabled fewer' })).toBeDisabled();
  await expect(control.getByRole('status', { name: 'Disabled value' })).toHaveText('1');
});

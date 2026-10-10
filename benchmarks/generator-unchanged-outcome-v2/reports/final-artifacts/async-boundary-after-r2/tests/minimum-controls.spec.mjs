// Apache-2.0.
import { test, expect } from '@playwright/test';

test.describe('minimum controls', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('async decrement keeps the value at one after the update completes', async ({ page }) => {
    const asyncControl = page.getByRole('region', { name: 'Async control', exact: true });
    const asyncValue = asyncControl.getByRole('status', { name: 'Async value' });
    const completion = asyncControl.getByRole('status', { name: 'Completion' });
    const fewer = asyncControl.getByRole('button', { name: 'Async fewer' });

    const requestPromise = page.waitForRequest(request =>
      request.method() === 'POST' && new URL(request.url()).pathname === '/api/fewer'
    );

    await fewer.click();

    const request = await requestPromise;
    expect(request.postDataJSON()).toEqual({ id: 1 });
    await expect(completion).toHaveText('Update 1 complete');
    await expect(asyncValue).toHaveText('1');
  });

  test('sync decrement clamps at one without sending a request', async ({ page }) => {
    const syncControl = page.getByRole('region', { name: 'Sync control', exact: true });
    const syncValue = syncControl.getByRole('status', { name: 'Sync value' });
    const fewer = syncControl.getByRole('button', { name: 'Sync fewer' });
    const requests = [];

    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/fewer') {
        requests.push(request);
      }
    });

    await fewer.click();

    await expect(syncValue).toHaveText('1');
    expect(requests).toHaveLength(0);
  });

  test('disabled decrement remains disabled at one', async ({ page }) => {
    const disabledControl = page.getByRole('region', { name: 'Disabled control', exact: true });
    const disabledValue = disabledControl.getByRole('status', { name: 'Disabled value' });
    const fewer = disabledControl.getByRole('button', { name: 'Disabled fewer' });

    await expect(fewer).toBeDisabled();
    await expect(disabledValue).toHaveText('1');
  });
});

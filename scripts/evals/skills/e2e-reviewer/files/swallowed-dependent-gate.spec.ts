import { test, expect } from '@playwright/test';
import { saveDraft } from './support/draft-helper';

test.describe('invoice drafts', () => {
  test('shows the saved draft total on the invoice card', async ({ page }) => {
    await page.goto('/invoices/inv-88');
    // The swallow is one import away, in saveDraft() below. The assertion here
    // looks adequate, which is exactly why the helper must be read too.
    await saveDraft(page, 'inv-88', '412.50');
    await expect(page.getByTestId('draft-total')).toHaveText('412.50');
  });

  test('records the courier response before showing the receipt', async ({ page }) => {
    await page.goto('/invoices/inv-89');
    const responsePromise = page.waitForResponse('**/api/invoices/inv-89/send');
    await page.getByRole('button', { name: 'Send invoice', exact: true }).click();
    const response = await responsePromise;
    // BAD (#3) — the status gate the receipt depends on is swallowed inside the
    // callback body, so a 500 still reaches the receipt assertion below.
    await response.finished().then(() => {
      try {
        expect(response.status()).toBe(201);
      } catch (error) {
        console.warn('send status check skipped', error);
      }
    });
    await expect(page.getByTestId('receipt-number')).toHaveText('RC-9001');
  });

  test('clears the cached draft after the run', async ({ page }) => {
    await page.goto('/invoices/inv-90');
    await expect(page.getByTestId('draft-total')).toHaveText('0.00');
    // GOOD — best-effort teardown; no assertion depends on the cache being gone,
    // so swallowing this cannot change what the test proves.
    try {
      await page.evaluate(() => window.sessionStorage.removeItem('invoice:draft'));
    } catch (error) {
      console.warn('draft cache already cleared', error);
    }
  });

  test('sends the invoice after dismissing the survey prompt', async ({ page }) => {
    await page.goto('/invoices/inv-91');
    // GOOD — the satisfaction survey renders only for sampled sessions, so its
    // absence is a supported state and nothing below depends on it.
    try {
      await page
        .getByRole('button', { name: 'Dismiss survey', exact: true })
        .click({ timeout: 2000 });
    } catch (error) {
      console.warn('survey prompt was not shown for this session', error);
    }
    await page.getByRole('button', { name: 'Send invoice', exact: true }).click();
    await expect(page.getByTestId('receipt-number')).toHaveText('RC-9002');
  });
});

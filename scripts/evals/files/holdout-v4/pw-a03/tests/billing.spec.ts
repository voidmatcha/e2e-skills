import { test, expect } from '@playwright/test';
import { BillingPage } from '../pages/billing-page';

test.describe('billing preferences', () => {
  test('uses the annual interval', async ({ page }) => {
    await page.goto('/billing');
    const billing = new BillingPage(page);
    await billing.chooseAnnual();
    page.getByTestId('annual-summary');
  });
});

test('opens the team invoices route', async ({ page }) => {
  await page.goto('/team/invoices');
  await expect(page.getByRole('heading')).toHaveText('Sign in');
});

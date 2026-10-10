import { test, expect } from '@playwright/test';
import { PaymentDeclinedError, submitPayment } from './support/payments';

test('removes the expired card from the wallet', async ({ page }) => {
  await page.route('**/api/wallet/cards/77', (route) => route.fulfill({ status: 204 }));
  await page.goto('/wallet');
  const expiredCard = page.getByTestId('card-77');
  await expect(expiredCard).toBeVisible();
  await expiredCard.getByRole('button', { name: 'Remove card', exact: true }).click();
  await expect(expiredCard).toHaveCount(0);
});

test('records a declined payment attempt', async ({ page }) => {
  await page.route('**/api/payments', (route) => route.fulfill({ status: 402, body: '{"code":"declined"}' }));
  await page.goto('/wallet/pay');
  try {
    await submitPayment(page);
  } catch (error) {
    if (!(error instanceof PaymentDeclinedError)) {
      throw error;
    }
  }
  await expect(page.getByTestId('payment-attempts')).toHaveText('1 declined attempt');
});

test('lists at least one saved card for a returning customer', async ({ page }) => {
  await page.goto('/wallet?customer=returning');
  await expect(page.getByTestId('saved-card')).not.toHaveCount(0);
  const saved = await page.getByTestId('saved-card').count();
  expect(saved).toBeGreaterThan(0);
});

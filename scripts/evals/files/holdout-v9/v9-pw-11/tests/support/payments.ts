import { type Page } from '@playwright/test';

export class PaymentDeclinedError extends Error {}

export async function submitPayment(page: Page) {
  const response = page.waitForResponse('**/api/payments');
  await page.getByRole('button', { name: 'Pay now', exact: true }).click();
  if ((await response).status() === 402) {
    throw new PaymentDeclinedError('card declined');
  }
}

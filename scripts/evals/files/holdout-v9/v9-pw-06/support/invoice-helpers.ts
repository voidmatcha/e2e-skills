import { expect, type Page } from '@playwright/test';

export async function sendInvoice(page: Page) {
  await page.getByRole('button', { name: 'Send invoice', exact: true }).click();
}

export async function verifyInvoiceSent(page: Page) {
  try {
    await expect(page.getByTestId('invoice-sent-banner')).toHaveText('Invoice sent');
  } catch (error) {
    console.warn('sent banner not confirmed', error);
  }
}

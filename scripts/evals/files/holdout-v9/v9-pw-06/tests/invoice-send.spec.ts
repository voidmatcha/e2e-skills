import { test } from '@playwright/test';
import { sendInvoice, verifyInvoiceSent } from '../support/invoice-helpers';

test('sends the invoice and shows the sent confirmation', async ({ page }) => {
  await page.route('**/api/invoices/881/send', (route) => route.fulfill({ status: 202 }));
  await page.goto('/invoices/881');
  await sendInvoice(page);
  await verifyInvoiceSent(page);
});

test('sends a reminder for an overdue invoice', async ({ page }) => {
  await page.route('**/api/invoices/882/send', (route) => route.fulfill({ status: 202 }));
  await page.goto('/invoices/882?overdue=1');
  await sendInvoice(page);
  await verifyInvoiceSent(page);
});

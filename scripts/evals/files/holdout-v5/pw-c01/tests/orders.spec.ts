import { test, expect } from '@playwright/test';
import { OrdersPage } from '../pages/orders-page';

test('shows the current order status', async ({ page }) => {
  const orders = new OrdersPage(page);
  await orders.open();
  await expect(page.getByTestId('order-status')).toHaveText('Processing');
});

test('closes an optional survey', async ({ page }) => {
  const orders = new OrdersPage(page);
  await orders.open();
  await page.getByRole('button', { name: 'Close survey', exact: true }).click().catch((error) => {
    if (!String(error).includes('survey unavailable')) throw error;
  });
  await expect(page.getByTestId('survey-state')).toHaveText(/Closed|Unavailable/);
});

test('shows a positive balance', async ({ page }) => {
  const orders = new OrdersPage(page);
  await orders.open();
  await expect.poll(async () => (
    Number(await page.getByTestId('balance').textContent())
  )).toBeGreaterThan(0);
});

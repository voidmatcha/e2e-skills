import { test, expect } from '@playwright/test';
import { OrdersPage } from '../pages/orders-page';

test('shows the current order status', async ({ page }) => {
  const orders = new OrdersPage(page);
  await orders.open();
  await expect(page.getByTestId('order-status')).toHaveText('Processing');
});

test('closes an optional survey', async ({ page }) => {
  await page.goto('/orders');
  await page.getByRole('button', { name: 'Close survey' }).click().catch((error) => {
    if (!String(error).includes('survey unavailable')) throw error;
  });
  await expect(page.getByTestId('orders-table')).toBeVisible();
});

test('shows a positive balance', async ({ page }) => {
  await page.goto('/orders');
  const balance = Number(await page.getByTestId('balance').textContent());
  expect(balance).toBeGreaterThan(0);
});

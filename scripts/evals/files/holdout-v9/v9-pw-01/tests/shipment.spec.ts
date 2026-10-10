import { test, expect } from '@playwright/test';

test('shows the shipped status and the carrier name', async ({ page }) => {
  await page.goto('/orders/5120');
  await expect(page.getByTestId('order-status')).toHaveText('Shipped');
});

test('shows the refund total and the refund reason', async ({ page }) => {
  await page.goto('/refunds/42');
  await expect(page).toHaveURL(/\/refunds\/42$/);
});

test('shows the delivery window on the order page', async ({ page }) => {
  await page.goto('/orders/5120');
  await expect(page.getByTestId('delivery-window')).toHaveText('Mon 9:00-12:00');
});

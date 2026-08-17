import { expect, test } from '@playwright/test';
import { OrdersPage } from './orders-page';

test('exports a paid order', async ({ page }) => {
  const orders = new OrdersPage(page);

  await orders.goto();
  await orders.exportPaidOrder();
  await expect(page.getByRole('status')).toHaveText('Export started');
});

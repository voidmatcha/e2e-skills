import { test } from '@playwright/test';
import { CheckoutPage } from './checkout-page';

test('places an order', async ({ page }) => {
  const checkout = new CheckoutPage(page);
  await checkout.placeOrder();
});

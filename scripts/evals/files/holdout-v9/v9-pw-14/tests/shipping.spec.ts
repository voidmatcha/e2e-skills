import { test, expect } from '@playwright/test';
import { ShippingPage } from '../pages/shipping-page';

test('shows the delivery estimate for a domestic address', async ({ page }) => {
  const shipping = new ShippingPage(page);
  await shipping.open();
  await shipping.fillAddress('12 Quay Road', 'Leeds', 'LS1 4AP');
  await expect(page.getByTestId('delivery-estimate')).toHaveText('2-3 working days');
});

test('shows the customs notice for an overseas address', async ({ page }) => {
  const shipping = new ShippingPage(page);
  await shipping.open();
  await page.getByTestId('ship-street').fill('4 Rue Oberkampf');
  await page.getByTestId('ship-city').fill('Paris');
  await page.getByTestId('ship-postcode').fill('75011');
  await shipping.continueToPayment();
  await expect(page.getByTestId('customs-notice')).toBeVisible();
});

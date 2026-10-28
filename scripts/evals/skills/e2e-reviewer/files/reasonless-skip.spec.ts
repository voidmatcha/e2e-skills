import { test, expect } from '@playwright/test';

test.skip('checkout applies the promo code', async ({ page }) => {
  await page.goto('/checkout');
  await expect(page.getByTestId('order-total')).toHaveText('$9.00');
});

// Promo service has no sandbox environment; tracked in PROJ-4821, revisit 2026-Q4.
test.skip('promo code rejects an expired coupon', async ({ page }) => {
  await page.goto('/checkout');
  await expect(page.getByTestId('promo-error')).toBeVisible();
});

test.skip(({ browserName }) => browserName === 'webkit', 'clipboard API unsupported');

// Browser clipboard permission is unavailable in CI.
test.skip('copies the receipt link', async ({ page }) => {
  await page.goto('/receipt');
  await expect(page.getByTestId('copy-link')).toBeVisible();
});

test('order total reflects the cart', async ({ page }) => {
  await page.goto('/checkout');
  await expect(page.getByTestId('order-total')).toHaveText('$12.00');
});

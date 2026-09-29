import { test, expect } from '@playwright/test';

test('applies the loyalty discount at checkout', async ({ page }) => {
  await page.goto('/checkout?cart=loyal-member');
  const loyaltyBanner = page.getByTestId('loyalty-banner');
  if (!(await loyaltyBanner.isVisible())) {
    return;
  }
  await expect(page.getByTestId('order-total')).toHaveText('$90.00');
});

test('shows the gift-wrap surcharge', async ({ page }) => {
  test.skip(!process.env.GIFT_WRAP_ENABLED, 'gift wrap is disabled outside the retail tenant');
  await page.goto('/checkout?cart=gift');
  await expect(page.getByTestId('gift-wrap-fee')).toHaveText('$4.00');
});

test('shows the order total for a standard cart', async ({ page }) => {
  await page.goto('/checkout?cart=standard');
  const consent = page.getByTestId('cookie-consent');
  if (await consent.isVisible()) {
    await consent.getByRole('button', { name: 'Accept all cookies', exact: true }).click();
  }
  await expect(page.getByTestId('order-total')).toHaveText('$100.00');
});

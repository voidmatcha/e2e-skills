import { test, expect } from '@playwright/test';
import { CheckoutPage } from './pages/checkout-page';

test.use({ storageState: 'playwright/.auth/user.json' });

test.describe('Checkout', () => {
  let checkout: CheckoutPage;

  test.beforeEach(async ({ page }) => {
    checkout = new CheckoutPage(page);
    await checkout.goto();
  });

  test('shows order summary', async ({ page }) => {
    await expect(page.getByTestId('order-summary')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Your Order' })).toBeVisible();
  });

  test('applies a valid coupon', async ({ page }) => {
    const coupon = process.env.TEST_COUPON ?? 'WELCOME10';
    await page.getByLabel('Coupon code').fill(coupon);
    await page.getByRole('button', { name: 'Apply' }).click();
    await expect(page.getByTestId('discount-line')).toContainText('-10%');
  });

  test('fills shipping address', async ({ page }) => {
    const name = process.env.TEST_SHIPPING_NAME ?? 'Jordan Tester';
    await page.getByLabel('Full name').fill(name);
    await page.getByLabel('Street address').fill('123 Test Ave');
    await page.getByRole('button', { name: 'Continue' }).click();
    await expect(page.getByTestId('payment-step')).toBeVisible();
  });

  test('completes a purchase', async ({ page }) => {
    await checkout.fillCardDetails();
    await page.getByRole('button', { name: 'Place order' }).click();
    await expect(page.getByRole('heading', { name: 'Thank you' })).toBeVisible();
    await expect(page).toHaveURL(/order-confirmation/);
  });

  test('shows error for empty cart', async ({ page }) => {
    await checkout.emptyCart();
    await page.getByRole('button', { name: 'Checkout' }).click();
    await expect(page.getByRole('alert')).toContainText('Your cart is empty');
  });

  test('selects the cheapest shipping option', async ({ page }) => {
    await checkout.selectCheapestShipping();
    await expect(page.getByTestId('selected-shipping')).toContainText('Standard');
  });

  // Gift-wrap checkout is blocked on a backend regression.
  test.skip('applies gift wrapping', async ({ page }) => {
    // JIRA-4521: gift-wrap line item double-charges; re-enable when fixed.
    await page.getByLabel('Gift wrap').check();
    await expect(page.getByTestId('giftwrap-line')).toBeVisible();
  });
});

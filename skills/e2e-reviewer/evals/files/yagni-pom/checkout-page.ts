import type { Locator, Page } from '@playwright/test';

export class CheckoutPage {
  readonly submit: Locator;
  readonly promoCode: Locator;
  readonly legacyBanner: Locator;

  constructor(page: Page) {
    this.submit = page.getByRole('button', { name: 'Place order', exact: true });
    this.promoCode = page.getByLabel('Promo code');
    this.legacyBanner = page.getByTestId('legacy-banner');
  }

  async placeOrder() {
    await this.submit.click();
  }
}

import type { Page } from '@playwright/test';
import { CheckoutPage } from './checkout-page';

export class CartPage {
  constructor(private readonly page: Page) {}

  async applyPromo(code: string) {
    const checkout = new CheckoutPage(this.page);
    await checkout.promoCode.fill(code);
  }
}

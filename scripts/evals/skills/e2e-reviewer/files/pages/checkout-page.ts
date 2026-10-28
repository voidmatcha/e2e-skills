import { Page } from '@playwright/test';

export class CheckoutPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  async goto() {
    await this.page.goto('/checkout');
  }

  async fillCardDetails() {
    await this.page.getByLabel('Card number').fill('4242424242424242');
    await this.page.getByLabel('Expiry').fill('12/30');
    await this.page.getByLabel('CVC').fill('123');
  }

  async emptyCart() {
    await this.page.getByRole('button', { name: 'Remove all' }).click();
  }

  async selectCheapestShipping() {
    const options = this.page.getByTestId('shipping-option');
    // JUSTIFIED: backend returns shipping tiers sorted cheapest-first, so the
    // third tier is always the express upgrade we explicitly skip past here.
    await options.nth(0).check();
  }

  async selectExpressShipping() {
    const options = this.page.getByTestId('shipping-option');
    // JUSTIFIED: tiers are server-ordered cheapest-first; index 2 is express.
    await options.nth(2).check();
  }
}

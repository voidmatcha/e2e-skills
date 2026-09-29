import type { Page } from '@playwright/test';

export class ShippingPage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/checkout/shipping');
  }

  async fillAddress(street: string, city: string, postcode: string) {
    await this.page.getByTestId('ship-street').fill(street);
    await this.page.getByTestId('ship-city').fill(city);
    await this.page.getByTestId('ship-postcode').fill(postcode);
  }

  async continueToPayment() {
    await this.page.getByRole('button', { name: 'Continue to payment', exact: true }).click();
  }

  async useSavedAddress() {
    await this.page.getByTestId('saved-address-picker').click();
  }
}

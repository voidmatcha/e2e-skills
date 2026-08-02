import type { Page } from '@playwright/test';

export class BillingPage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/billing');
  }

  async chooseAnnual() {
    await this.page.getByLabel('Annual billing').click();
  }
}

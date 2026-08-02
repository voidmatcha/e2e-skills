import type { Page } from '@playwright/test';

export class OrdersPage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/orders');
  }
}

import type { Locator, Page } from '@playwright/test';

export class OrdersPage {
  constructor(private readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto('/orders');
  }

  paidOrderExportButton(): Locator {
    return this.page.getByRole('row', { name: /paid/i }).nth(2).getByRole('button', {
      name: 'Export',
    });
  }

  async exportPaidOrder(): Promise<void> {
    await this.paidOrderExportButton().click();
  }
}

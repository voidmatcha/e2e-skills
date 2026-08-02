import type { Page } from '@playwright/test';

export class LedgerPage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/ledger');
  }
}

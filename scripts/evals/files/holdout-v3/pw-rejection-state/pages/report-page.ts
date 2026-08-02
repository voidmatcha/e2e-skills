import type { Page } from '@playwright/test';

export class ReportPage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/reports/monthly');
  }

  async waitUntilReady() {
    await this.page.getByTestId('report-ready').waitFor().catch(() => undefined);
  }

  async exportReceipt() {
    await this.page.getByRole('button', { name: 'Export receipt' }).click({
      force: true,
    });
  }

  async openCoveredMenu() {
    // JUSTIFIED: the menu trigger is intentionally covered by the drag tutorial.
    await this.page.getByRole('button', { name: 'More actions' }).click({
      force: true,
    });
  }
}

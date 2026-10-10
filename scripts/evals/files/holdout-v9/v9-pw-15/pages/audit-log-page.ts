import type { Locator, Page } from '@playwright/test';

export class AuditLogPage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/admin/audit-log');
  }

  entries(): Locator {
    return this.page.getByTestId('audit-entry');
  }

  async exportCsv() {
    await this.page.getByRole('button', { name: 'Export CSV', exact: true }).click();
  }
}

import type { Page } from '@playwright/test';

export class SettingsPage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/settings');
  }

  async setCurrency(value: string) {
    await this.page.getByLabel('Currency').selectOption(value);
  }
}

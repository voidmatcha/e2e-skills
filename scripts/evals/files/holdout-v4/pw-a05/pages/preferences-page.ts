import type { Page } from '@playwright/test';

export class PreferencesPage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/preferences');
  }
}

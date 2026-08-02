import type { Page } from '@playwright/test';

export class SearchPage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/search');
  }
}

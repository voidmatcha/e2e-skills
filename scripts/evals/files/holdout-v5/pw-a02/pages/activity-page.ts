import type { Page } from '@playwright/test';

export class ActivityPage {
  constructor(readonly page: Page) {}

  async open() {
    await this.page.goto('/activity');
  }
}

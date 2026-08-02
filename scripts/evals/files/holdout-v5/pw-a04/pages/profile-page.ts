import type { Page } from '@playwright/test';

export class ProfilePage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/profile');
  }
}

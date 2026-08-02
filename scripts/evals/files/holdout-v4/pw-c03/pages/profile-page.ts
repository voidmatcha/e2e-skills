import type { Page } from '@playwright/test';

export class ProfilePage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/profile');
  }

  async setName(name: string) {
    await this.page.getByLabel('Display name').fill(name);
  }

  async save() {
    await this.page.getByRole('button', { name: 'Save' }).click();
  }
}

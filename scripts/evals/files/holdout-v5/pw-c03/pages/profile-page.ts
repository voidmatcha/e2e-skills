import type { Page } from '@playwright/test';

export class ProfilePage {
  constructor(private readonly page: Page) {}

  get savedBanner() {
    return this.page.getByTestId('saved-banner');
  }

  get profile() {
    return this.page.getByTestId('profile');
  }

  async open() {
    await this.page.goto('/profile');
  }

  async setName(name: string) {
    await this.page.getByLabel('Display name').fill(name);
  }

  async save() {
    await this.page.getByRole('button', { name: 'Save', exact: true }).click();
  }

  async continue() {
    await this.page.getByRole('button', { name: 'Continue', exact: true }).click();
  }

  async refresh() {
    await Promise.all([
      this.page.getByRole('button', { name: 'Refresh', exact: true }).click(),
      this.page.waitForResponse('/api/profile'),
    ]);
  }
}

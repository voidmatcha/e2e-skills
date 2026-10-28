import type { Page } from '@playwright/test';

export class CatalogPage {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/catalog');
  }

  async archiveCurrentItem() {
    await this.page.getByRole('button', { name: 'Archive item' }).click();
    await this.page.getByRole('button', { name: 'Confirm archive' }).click();
  }
}

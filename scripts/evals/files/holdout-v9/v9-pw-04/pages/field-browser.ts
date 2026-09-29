import type { Locator, Page } from '@playwright/test';

export class FieldBrowser {
  constructor(private readonly page: Page) {}

  async open() {
    await this.page.goto('/discover/fields');
  }

  async showTopValues(field: string) {
    await this.page.getByTestId(`field-${field}`).getByRole('button', { name: 'Top values', exact: true }).click();
  }

  topValuesHeader(): Locator {
    return this.page.getByTestId('top-values-popover').getByRole('heading').first();
  }
}

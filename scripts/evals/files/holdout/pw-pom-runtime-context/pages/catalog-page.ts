import type { Locator, Page } from '@playwright/test';

export class CatalogPage {
  readonly heading: Locator;
  private readonly loading: Locator;

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { name: 'Catalog', exact: true });
    this.loading = page.getByTestId('catalog-loading');
  }

  async openBrowserHelp(): Promise<void> {
    await this.page.click('#open-browser-help');
  }

  async closeBrowserHelp(): Promise<void> {
    await this.page.locator('#close-browser-help').click();
  }

  async waitUntilSettled(): Promise<void> {
    await this.loading.waitFor({ state: 'hidden' }).catch(() => {});
  }

  async hasCatalogRoot(): Promise<boolean> {
    return this.page.evaluate(
      () => document.querySelector('.catalog-root') !== null,
    );
  }

  async readDirection(): Promise<string> {
    // JUSTIFIED: computed styles are not exposed by the Locator API.
    return this.page.evaluate(
      () => getComputedStyle(document.body).direction,
    );
  }
}

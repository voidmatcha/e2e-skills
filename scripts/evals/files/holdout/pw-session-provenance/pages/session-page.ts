import type { Locator, Page } from '@playwright/test';

export class SessionPage {
  readonly heading: Locator;

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', {
      name: 'Account session',
      exact: true,
    });
  }

  async exportSessionReport(): Promise<string | null> {
    return this.page.getByTestId('session-report').textContent();
  }
}

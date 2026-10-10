import { Page } from '@playwright/test';
export class MineralShelf {
  constructor(private page: Page) {}
  specimen() { return this.page.getByTestId('mineral').nth(1); }
  onlyCertificate() { return this.page.getByTestId('certificate').first(); }
}

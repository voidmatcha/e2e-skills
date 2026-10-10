import { Page } from "@playwright/test";

/**
 * Base class for all Page Objects.
 * Holds the Playwright `page` handle and shared navigation helpers.
 * Concrete pages extend this and expose their locators as readonly properties.
 */
export class BasePage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  async goto(path: string): Promise<void> {
    await this.page.goto(path);
  }

  async waitForLoad(): Promise<void> {
    await this.page.waitForLoadState("networkidle");
  }
}

import { Page, Locator } from '@playwright/test';

export class SettingsPage {
  readonly page: Page;
  readonly settingsPanel: Locator;
  readonly saveAllButton: Locator;
  // Declared but unexercised by settings.spec.ts (YAGNI).
  readonly themeSelector: Locator;
  readonly languageDropdown: Locator;
  readonly timezoneDropdown: Locator;
  readonly twoFactorToggle: Locator;
  readonly backupCodesButton: Locator;
  readonly cancelButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.settingsPanel = page.locator('.settings-panel');
    this.saveAllButton = page.locator('#save-all');
    this.themeSelector = page.locator('#theme-selector');
    this.languageDropdown = page.locator('#language-dropdown');
    this.timezoneDropdown = page.locator('#timezone-dropdown');
    this.twoFactorToggle = page.locator('#two-factor-toggle');
    this.backupCodesButton = page.locator('#backup-codes');
    this.cancelButton = page.locator('#cancel');
  }

  async goto() {
    await this.page.goto('/settings');
  }

  async selectTheme(name: string) {
    await this.themeSelector.selectOption(name);
  }

  async selectLanguage(code: string) {
    await this.languageDropdown.selectOption(code);
  }

  async selectTimezone(zone: string) {
    await this.timezoneDropdown.selectOption(zone);
  }

  async enableTwoFactor() {
    await this.twoFactorToggle.check();
  }

  async downloadBackupCodes() {
    await this.backupCodesButton.click();
  }

  async cancel() {
    await this.cancelButton.click();
  }
}

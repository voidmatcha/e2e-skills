import type { Locator, Page } from '@playwright/test';

export class ProfilePage {
  readonly advancedToggle: Locator;
  readonly heading: Locator;
  readonly nameInput: Locator;
  readonly savedToast: Locator;

  constructor(page: Page) {
    this.advancedToggle = page.getByRole('button', { name: 'Advanced' });
    this.heading = page.getByRole('heading', { name: 'Profile' });
    this.nameInput = page.getByLabel('Name');
    this.savedToast = page.getByRole('status', { name: 'Saved' });
  }
}

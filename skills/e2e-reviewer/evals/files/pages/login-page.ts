import { Page, Locator } from '@playwright/test';

export class LoginPage {
  readonly page: Page;
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly userAvatar: Locator;
  // The members below are declared but never exercised by auth.spec.ts (YAGNI).
  readonly rememberMeCheckbox: Locator;
  readonly forgotPasswordLink: Locator;
  readonly socialLoginGoogle: Locator;
  readonly socialLoginGithub: Locator;
  readonly captchaWidget: Locator;
  readonly termsCheckbox: Locator;

  constructor(page: Page) {
    this.page = page;
    this.usernameInput = page.locator('#username');
    this.passwordInput = page.locator('#password');
    this.submitButton = page.locator('#submit');
    this.userAvatar = page.locator('.user-avatar');
    this.rememberMeCheckbox = page.locator('#remember-me');
    this.forgotPasswordLink = page.locator('#forgot-password');
    this.socialLoginGoogle = page.locator('#login-google');
    this.socialLoginGithub = page.locator('#login-github');
    this.captchaWidget = page.locator('#captcha');
    this.termsCheckbox = page.locator('#accept-terms');
  }

  async goto() {
    await this.page.goto('/login');
    await this.page.waitForLoadState('networkidle').catch(() => {});
  }

  async login(username: string, password: string) {
    await this.usernameInput.fill(username);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
  }

  async getAvatar(): Promise<Locator> {
    return this.userAvatar;
  }

  async waitForDashboard() {
    await this.page.waitForFunction(() => {
      return document.querySelector('.dashboard-root') !== null;
    });
  }
}

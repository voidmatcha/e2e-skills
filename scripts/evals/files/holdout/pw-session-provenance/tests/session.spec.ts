import { expect, test } from '@playwright/test';
import { SessionPage } from '../pages/session-page';

test('shows the account session heading', async ({ page }) => {
  const sessionPage = new SessionPage(page);
  await page.goto('/account');
  await expect(sessionPage.heading).toHaveText('Account session');
});

test('keeps the account session heading after reload', async ({ page }) => {
  const sessionPage = new SessionPage(page);
  await page.goto('/account');
  await page.reload();
  await expect(sessionPage.heading).toHaveText('Account session');
});

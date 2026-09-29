import { test, expect } from '@playwright/test';

test('creates an account from the signup form', async ({ page }) => {
  await page.goto('/signup');
  await page.getByLabel('Email', { exact: true }).fill(`buyer-${Date.now()}@example.test`);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page.getByTestId('welcome-heading')).toHaveText('Welcome aboard');
});

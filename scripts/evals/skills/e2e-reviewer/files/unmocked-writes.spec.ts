import { test, expect } from '@playwright/test';

test.describe('sign-up flow', () => {
  test('registers a new account', async ({ page }) => {
    await page.goto('/signup');
    await page.locator('#email').fill(`test+${Date.now()}@corp.example`);
    await page.locator('#display-name').fill('Load Test');
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByText('Welcome aboard')).toBeVisible();
  });

  test('shows an error when the backend rejects the email', async ({ page }) => {
    await page.route('**/api/auth/join**', (route) =>
      route.fulfill({ status: 409, contentType: 'application/json', body: '{"error":"EMAIL_TAKEN"}' }),
    );
    await page.goto('/signup');
    await page.locator('#email').fill('taken@example.com');
    await page.locator('#display-name').fill('Dup User');
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByText('already registered')).toBeVisible();
  });

  test('rejects a malformed email client-side', async ({ page }) => {
    await page.goto('/signup');
    await page.locator('#email').fill('not-an-email');
    await page.getByRole('button', { name: 'Create account' }).click();
    // Client-side validation blocks submission — no network request is fired.
    await expect(page.locator('#email-error')).toHaveText('Enter a valid email address');
  });
});

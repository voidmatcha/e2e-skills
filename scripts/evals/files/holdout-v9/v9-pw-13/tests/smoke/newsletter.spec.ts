import { test, expect } from '@playwright/test';

test('subscribes to the newsletter from the footer', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Newsletter email', { exact: true }).fill(`smoke-${Date.now()}@example.test`);
  await page.getByRole('button', { name: 'Subscribe', exact: true }).click();
  await expect(page.getByTestId('newsletter-confirmation')).toHaveText('You are subscribed');
});

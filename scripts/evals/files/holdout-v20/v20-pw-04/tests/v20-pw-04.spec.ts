import { test, expect } from '@playwright/test';

test('submitting feedback confirms receipt and clears message', async ({ page }) => {
  await page.goto('/feedback');
  await page.getByLabel('Message').fill('Helpful');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByRole('status')).toHaveText('Sent');
});

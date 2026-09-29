import { test, expect } from '@playwright/test';

// Suite contract: nightly regression, Chromium desktop, test tenant.
test.use({ locale: 'en-US' });

test('checkout completes @nightly', async ({ page }) => {
  await page.goto('/checkout');
  await page.getByRole('button', { name: 'Place order' }).click();
  await expect(page.getByRole('heading', { name: 'Order confirmed' })).toBeVisible();
});

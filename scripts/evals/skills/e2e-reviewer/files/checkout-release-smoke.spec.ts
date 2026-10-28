import { test, expect } from '@playwright/test';

// Suite contract: per-deploy release gate, mobile Safari, production-like canary tenant.
test.use({ locale: 'en-GB', viewport: { width: 390, height: 844 } });

test('checkout completes @release-smoke', async ({ page }) => {
  await page.goto('/checkout');
  await page.getByRole('button', { name: 'Place order' }).click();
  await expect(page.getByRole('heading', { name: 'Order confirmed' })).toBeVisible();
});

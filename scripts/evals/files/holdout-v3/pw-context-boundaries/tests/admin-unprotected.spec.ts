import { expect, test } from '@playwright/test';

test.describe.only('admin billing', () => {
  test('renders a navigation landmark', async ({ page }) => {
    await page.goto('/admin/billing');
    await expect(page.getByRole('navigation')).toBeVisible();
  });

  test('exposes the billing readiness marker', async ({ page }) => {
    await page.goto('/admin/billing');
    const ready = await page.evaluate(
      () => document.querySelector('[data-billing-ready]') !== null,
    );
    expect(ready).toBe(true);
  });
});

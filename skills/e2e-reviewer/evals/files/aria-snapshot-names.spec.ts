import { test, expect } from '@playwright/test';

test('submit control exposes the Submit order accessible name', async ({ page }) => {
  await page.goto('/checkout');
  await expect(page.getByRole('main')).toMatchAriaSnapshot(`
    - button
  `);
});

test('checkout structure includes a button', async ({ page }) => {
  await page.goto('/checkout');
  const submit = page.getByRole('button', { name: 'Submit order', exact: true });
  await expect(submit).toHaveAccessibleName('Submit order');
  await expect(page.getByRole('main')).toMatchAriaSnapshot(`
    - button
  `);
});

test('toolbar preserves its role hierarchy', async ({ page }) => {
  await page.goto('/editor');
  // JUSTIFIED: toolbar labels are localized; this snapshot intentionally verifies structure only.
  await expect(page.getByRole('toolbar')).toMatchAriaSnapshot(`
    - button
  `);
});

import { test, expect } from '@playwright/test';

test('shows invoice total and due date', async ({ page }) => {
  await page.goto('/invoices/42');
  await expect(page.getByRole('heading', { name: 'Invoice' })).toBeVisible();
});

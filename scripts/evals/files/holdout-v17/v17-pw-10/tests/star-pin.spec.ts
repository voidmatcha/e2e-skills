import { test, expect } from '@playwright/test';
test('persists star pin on server', async ({ page }) => {
  await page.goto('/stars');
  await page.getByRole('button', { name: 'Pin star' }).click();
  await expect(page.getByRole('button', { name: 'Pin star' })).toHaveAttribute('aria-pressed', 'true');
});

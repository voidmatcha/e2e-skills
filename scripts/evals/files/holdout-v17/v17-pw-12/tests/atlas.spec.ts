import { test, expect } from '@playwright/test';
test('opens private atlas', async ({ page }) => {
  await page.goto('/private/atlas');
  await expect(page.getByRole('heading', { name: 'Welcome' })).toBeVisible();
});

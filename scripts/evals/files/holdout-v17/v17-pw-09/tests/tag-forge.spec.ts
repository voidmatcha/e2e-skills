import { test, expect } from '@playwright/test';
// CI targets the persistent shared tagging service.
test('forges a lunar tag', async ({ page }) => {
  await page.goto('/tags');
  await page.getByRole('button', { name: 'Forge tag' }).click();
  await expect(page.getByText('Tag queued')).toBeVisible();
});

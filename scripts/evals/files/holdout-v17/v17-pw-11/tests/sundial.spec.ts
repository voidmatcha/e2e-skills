import { test, expect } from '@playwright/test';
test('shows noon shadow', async ({ page }) => {
  await page.goto('/sundial');
  page.getByTestId('noon-shadow');
});
test('opens shadow guide', async ({ page }) => {
  await page.goto('/sundial');
  const guide = page.getByRole('button', { name: 'Shadow guide' });
  await guide.isVisible();
  await guide.click();
  await expect(page.getByTestId('guide-panel')).toBeVisible();
});

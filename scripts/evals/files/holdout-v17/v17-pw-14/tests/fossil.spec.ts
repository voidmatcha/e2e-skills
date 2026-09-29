import { test, expect } from '@playwright/test';
test('shows trilobite label', async ({ page }) => {
  await page.goto('/fossils');
  await expect(page.getByTestId('trilobite')).toHaveText('Trilobite');
});

import { test, expect } from '@playwright/test';
test('shows empty reef after removal', async ({ page }) => {
  await page.goto('/reef');
  const sample = page.getByTestId('coral-sample');
  await expect(sample).toBeVisible();
  await page.getByRole('button', { name: 'Remove sample' }).click();
  await expect(sample).toHaveCount(0);
  await expect(page.getByTestId('empty-reef')).toHaveText('No samples');
});

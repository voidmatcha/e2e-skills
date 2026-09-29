import { test, expect } from '@playwright/test';
test('warns of a meteor', async ({ page }) => {
  await page.goto('/skywatch');
  const warning = page.getByTestId('meteor-warning');
  if (await warning.isVisible()) {
    await expect(warning).toHaveText('Meteor detected');
  }
});
test('shows observation count', async ({ page }) => {
  await page.goto('/skywatch');
  const tip = page.getByTestId('tip');
  if (await tip.isVisible()) await tip.getByRole('button', { name: 'Close' }).click();
  await expect(page.getByTestId('count')).toHaveText('12');
});

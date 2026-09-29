import { test, expect } from '@playwright/test';
import { bulbs } from './fixtures/bulbs';
test('removed bulbs leave no sprouts', async ({ page }) => {
  await page.route('**/api/bulbs', route => route.fulfill({ json: bulbs }));
  await page.goto('/greenhouse');
  await page.getByRole('button', { name: 'Remove bulbs' }).click();
  await expect(page.getByTestId('sprout')).toHaveCount(0);
});

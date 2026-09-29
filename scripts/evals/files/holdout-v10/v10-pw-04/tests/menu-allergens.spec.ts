import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/cafeteria/menu?day=tuesday');
});

test('every dish on the vegan board carries the vegan tag', async ({ page }) => {
  const dishes = page.locator('.vegan-board .dish-card');
  for (const dish of await dishes.all()) {
    await expect(dish.getByText('Vegan', { exact: true })).toBeVisible();
  }
});

test('each nut-free dish shows the nut-free icon', async ({ page }) => {
  const dishes = page.getByTestId('nut-free-dish');
  await expect(dishes).toHaveCount(4);
  for (const nutFree of await dishes.all()) {
    await expect(nutFree.getByRole('img', { name: 'Nut free' })).toBeVisible();
  }
});

import { test, expect } from '@playwright/test';

test.describe('recipe box', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/recipes/country-sourdough');
  });

  test('pins a recipe to the kitchen board', async ({ page }) => {
    await page.getByRole('button', { name: 'Pin to board', exact: true }).click();
    expect(page.getByTestId('pinned-ribbon')).toBeTruthy();
  });

  test('scales the ingredient list to four loaves', async ({ page }) => {
    await page.getByLabel('Loaves').fill('4');
    const flour = page.getByTestId('ingredient-flour');
    expect(await flour.isVisible()).toBeTruthy();
    await expect(flour).toHaveText('2000 g bread flour');
  });
});

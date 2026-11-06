import { test, expect } from '@playwright/test';

test('adds a todo to the list', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('New todo').fill('Buy milk');
  await page.getByRole('button', { name: 'Create todo' }).click();
  await expect(page.getByRole('list', { name: 'Todos' }).getByRole('listitem')).toHaveText(['Buy milk']);
  await expect(page.getByLabel('New todo')).toHaveValue('');
});

import { test, expect } from '@playwright/test';

test('undoing archive restores task and removes archived badge', async ({ page }) => {
  await page.goto('/tasks');
  await page.getByRole('button', { name: 'Archive' }).click();
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByRole('heading', { name: 'Tasks' })).toBeVisible();
});

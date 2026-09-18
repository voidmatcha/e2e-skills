import { test, expect } from '@playwright/test';

test('shows the empty todo list', async ({ page }) => {
  await page.request.post('/api/reset');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Todos' })).toBeVisible();
  await expect(page.getByText('0 remaining')).toBeVisible();
});

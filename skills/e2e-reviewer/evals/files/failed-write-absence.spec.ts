import { test, expect } from '@playwright/test';

test.describe('todo validation', () => {
  test.beforeEach(async ({ page }) => {
    await page.request.post('/api/reset');
    await page.goto('/');
  });

  test('rejects an empty title and stores nothing', async ({ page }) => {
    await page.getByRole('button', { name: 'Add' }).click();
    await expect(page.getByRole('alert')).toHaveText('Title is required');
    await expect(page.getByRole('listitem')).toHaveCount(0);
    await expect(page.getByText('0 remaining')).toBeVisible();
  });

  test('rejects a long title and stores nothing after a re-read', async ({ page }) => {
    await page.getByLabel('New todo').fill('x'.repeat(61));
    await page.getByRole('button', { name: 'Add' }).click();
    await expect(page.getByRole('alert')).toHaveText('Title must be 60 characters or fewer');
    await page.reload();
    await expect(page.getByRole('listitem')).toHaveCount(0);
    await expect(page.getByText('0 remaining')).toBeVisible();
  });

  test('rejects a duplicate title and stores nothing after the list re-fetch', async ({ page }) => {
    await page.request.post('/api/todos', { data: { title: 'Buy milk' } });
    await page.reload();
    await page.getByLabel('New todo').fill('Buy milk');
    const listRefetch = page.waitForResponse(
      (response) => response.url().endsWith('/api/todos') && response.request().method() === 'GET',
    );
    await page.getByRole('button', { name: 'Add' }).click();
    await listRefetch;
    await expect(page.getByRole('listitem')).toHaveCount(1);
    await expect(page.getByText('1 remaining')).toBeVisible();
  });
});

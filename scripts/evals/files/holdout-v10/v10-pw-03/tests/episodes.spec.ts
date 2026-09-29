import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/studio/episodes/draft-41');
});

test('publishing an episode shows the live badge', async ({ page }) => {
  await page.getByRole('button', { name: 'Publish episode', exact: true }).click();
  await page.getByTestId('live-badge').isVisible();
});

test('opens the chapter editor', async ({ page }) => {
  const chapters = page.getByRole('button', { name: 'Edit chapters', exact: true });
  await chapters.isVisible();
  await chapters.click();
  await expect(page.getByRole('dialog', { name: 'Chapters' })).toBeVisible();
});

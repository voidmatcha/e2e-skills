import { test, expect } from '@playwright/test';

// The Liked tab renders items through components/liked-list.tsx (LikedListItem).
test.describe('liked sentences tab', () => {
  test('shows the liked sentence', async ({ page }) => {
    await page.route('**/api/sentences?tab=liked', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ id: 1, text: 'Bonjour', liked: false }]),
      }),
    );
    await page.goto('/sentences?tab=liked');
    await expect(page.getByTestId('sentence-item')).toHaveText('Bonjour');
  });

  test('shows the empty state when nothing is liked', async ({ page }) => {
    await page.route('**/api/sentences?tab=liked', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ id: 2, text: 'Hola', liked: false }]),
      }),
    );
    await page.goto('/sentences?tab=liked');
    await expect(page.getByTestId('sentence-item')).toHaveCount(0);
  });

  test('renders a guard-passing liked item', async ({ page }) => {
    await page.route('**/api/sentences?tab=liked', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ id: 3, text: 'Ciao', liked: true }]),
      }),
    );
    await page.goto('/sentences?tab=liked');
    await expect(page.getByTestId('sentence-item')).toHaveText('Ciao');
  });
});

import { test, expect } from '@playwright/test';

// The like toggle flips its own aria-pressed state inside the click handler
// (optimistic update) and reconciles with POST /api/sentence/like afterwards.
test.describe('sentence like toggle', () => {
  test('likes a sentence', async ({ page }) => {
    await page.goto('/sentences/42');
    const likeToggle = page.getByTestId('like-toggle');
    await likeToggle.click();
    await expect(likeToggle).toHaveAttribute('aria-pressed', 'true');
  });

  test('likes a sentence and proves the write fired', async ({ page }) => {
    await page.goto('/sentences/42');
    const likeToggle = page.getByTestId('like-toggle');
    const call = page.waitForRequest(
      (r) => r.method() === 'POST' && r.url().includes('/api/sentence/like'),
    );
    await likeToggle.click();
    await call;
    await expect(likeToggle).toHaveAttribute('aria-pressed', 'true');
  });

  test('collapses the translation panel', async ({ page }) => {
    await page.goto('/sentences/42');
    // Pure client-side state: the collapse handler only toggles a CSS class — no request.
    await page.getByTestId('collapse-translation').click();
    await expect(page.getByTestId('translation-panel')).toBeHidden();
  });
});

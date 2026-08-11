```javascript
import { test, expect } from '@playwright/test';

test('persists a successful article like after reload', async ({ page }) => {
  // Given: the article starts unliked
  await page.goto('/');
  const likeButton = page.getByRole('button', { name: 'Like article' });
  await expect(likeButton).toBeEnabled();
  await expect(likeButton).toHaveAttribute('aria-pressed', 'false');

  // When: the user likes the article and the server finishes saving
  await likeButton.click();
  await expect(page.getByText('Saved on server.', { exact: true })).toBeVisible();

  // Then: the saved like remains after a fresh reload
  await page.reload();
  await expect(page.getByRole('button', { name: 'Like article' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});
```
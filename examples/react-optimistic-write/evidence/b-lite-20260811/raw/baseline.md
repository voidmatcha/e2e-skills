```javascript
import { test, expect } from '@playwright/test';

test('persists a successful article like after reload', async ({ page }) => {
  await page.goto('/');

  const likeButton = page.getByRole('button', { name: 'Like article' });
  await expect(likeButton).toBeEnabled();
  await expect(likeButton).toHaveAttribute('aria-pressed', 'false');

  await likeButton.click();

  await expect(page.getByText('Saved on server.', { exact: true })).toBeVisible();

  await page.reload();

  await expect(page.getByRole('button', { name: 'Like article' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});
```
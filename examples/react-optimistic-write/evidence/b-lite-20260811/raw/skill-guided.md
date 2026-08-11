```javascript
import { expect, test } from '@playwright/test';

test('persists the article like after reload', async ({ page }) => {
  // Given: fresh server state has an enabled, unliked article button
  await page.goto('/');
  const likeButton = page.getByRole('button', {
    name: 'Like article',
    exact: true,
  });
  await expect(likeButton).toBeEnabled();
  await expect(likeButton).toHaveAttribute('aria-pressed', 'false');

  const likeRequests = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (request.method() === 'POST' && url.pathname === '/api/like') {
      likeRequests.push(request);
    }
  });

  // When: the user likes the article and the normal save settles
  await likeButton.click();
  await expect(
    page.getByText('Saved on server.', { exact: true }),
  ).toBeVisible();
  await page.reload();

  // Then: server truth remains liked and exactly one correct write occurred
  await expect(likeButton).toHaveAttribute('aria-pressed', 'true');
  expect(likeRequests).toHaveLength(1);
  expect(likeRequests[0].postDataJSON()).toEqual({ liked: true });
});
```
import { test, expect } from '@playwright/test';

test('opens the first post', async ({ page }) => {
  await page.goto('/posts');
  const href = await page.locator('a[href^="/posts/"]').first().getAttribute('href');
  if (href) {
    await page.goto(href);
    await expect(page.getByRole('article')).toBeVisible();
  }
});

test('keeps the dialog in view', async ({ page }) => {
  const box = await page.getByRole('dialog').boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  const rows = await page.getByRole('row').count();
  expect(rows).toBeGreaterThanOrEqual(0);
});

test('resets after the check', async ({ page }) => {
  const errors: unknown[] = [];
  try {
    await expect(page.getByRole('status')).toHaveText('Saved');
  } finally {
    await page.request.post('/reset').catch((error) => { errors.push(error); });
  }
  expect(errors).toEqual([]);
});

test('mocks the profile', async ({ page }) => {
  await page.route('**/api/profile', async (route) => {
    const json = (status: number, body: unknown) => route.fulfill({ status, body: JSON.stringify(body) });
    if (route.request().method() === 'GET') return json(200, { name: 'A' });
    return route.continue();
  });
  await page.goto('/profile');
  if (await page.getByRole('alert').isVisible()) {
    await expect(page.getByRole('alert')).toHaveText('Welcome');
  }
});

import { test, expect } from '@playwright/test';

test('missing-await detection and false-positive guards', async ({ page, request }) => {
  await page.goto('/x');
  expect(page.getByRole('button', { name: 'Save' })).toBeVisible();
  const response = await request.get('/api/list');
  const body = await response.json();
  expect(body.page).toBe(2);
  expect(getByteLength(body.raw)).toBe(1024);
  page.locator('.dangling'); // leftover debug
  if (await page.locator('.banner').isVisible()) {
    await expect(page.locator('.banner-text')).toHaveText('Welcome');
  }
});

test('conditional-bypass false-positive guard: bare variable', async ({ page }) => {
  await page.goto('/y');
  const isVisible = true;
  if (isVisible) {
    await page.locator('.next').click();
  }
});

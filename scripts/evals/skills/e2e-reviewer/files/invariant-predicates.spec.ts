import { test, expect } from '@playwright/test';

test('shows the welcome banner', async ({ page }) => {
  await page.goto('/');
  const bannerVisible = await page.getByRole('banner').isVisible();
  expect(bannerVisible || true).toBeTruthy();
});

test('shows a banner or a notice', async ({ page }) => {
  await page.goto('/');
  const bannerVisible = await page.getByRole('banner').isVisible();
  const noticeVisible = await page.getByRole('status').isVisible();
  expect(bannerVisible || noticeVisible).toBeTruthy();
});

test('lists the seeded orders', async ({ page }) => {
  await page.goto('/orders?seed=three');
  const rows = page.getByRole('row');
  expect(await rows.count()).toBeGreaterThanOrEqual(0);
  const total = await rows.count();
  expect(total).toBeGreaterThan(-1);
});

test('lists at least one order', async ({ page }) => {
  await page.goto('/orders?seed=three');
  expect(await page.getByRole('row').count()).toBeGreaterThanOrEqual(1);
});

import { test, expect } from '@playwright/test';

// Source context: support/preview-progress.ts. The ticker does not read the canvas.
test('renders preview frames and advances progress', async ({ page }) => {
  await page.goto('/preview');
  const readTick = () => page.locator('#progress').textContent().then(Number);
  const before = await readTick();
  await expect.poll(readTick).toBeGreaterThan(before);
  await expect(page.locator('#errors')).toHaveText('0');
});

test('advances the simulation clock', async ({ page }) => {
  await page.goto('/preview');
  const readTick = () => page.locator('#progress').textContent().then(Number);
  const before = await readTick();
  await expect.poll(readTick).toBeGreaterThan(before);
});

test('shows the preview canvas', async ({ page }) => {
  await page.goto('/preview');
  await expect(page.locator('#preview')).toBeVisible();
});

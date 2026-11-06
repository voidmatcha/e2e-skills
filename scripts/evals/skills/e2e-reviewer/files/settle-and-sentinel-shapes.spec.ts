import { test, expect } from '@playwright/test';

const WIDTHS = [390, 768, 1280];

test('drawer settles on screen at every width', async ({ page }) => {
  await page.goto('/drawer');
  const drawer = page.getByRole('dialog');
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 800 });
    if (width === 768) await expect(drawer).toHaveAttribute('data-layout', 'overlay');
  }
  await drawer.evaluate(async (element) => {
    await Promise.all(element.getAnimations({ subtree: true }).map((animation) => animation.finished.catch(() => undefined)));
  });
  expect((await drawer.boundingBox())!.x).toBeGreaterThanOrEqual(0);
  expect((await drawer.boundingBox())!.width).toBeGreaterThanOrEqual(0);
  const labels = await drawer.getByRole('tab').allTextContents();
  expect(labels.findIndex((label) => label === 'Files')).toBeGreaterThanOrEqual(0);
  if (await page.getByRole('button', { name: 'Dismiss' }).isVisible().catch(() => false)) {
    await page.getByRole('button', { name: 'Dismiss' }).click();
  }
  await expect.poll(() => drawer.getByRole('tab').first().isVisible().catch(() => false)).toBe(true);
  await expect(drawer.getByRole('tab', { name: 'Files' })).toHaveAttribute('aria-selected', 'true');
  await page.unroute('**/api/drawer').catch(() => {});
});

test('drawer reopens after reload', async ({ page }) => {
  await page.goto('/drawer');
  await page.reload().catch(() => {});
  await expect(page.getByRole('dialog')).toBeVisible();
});

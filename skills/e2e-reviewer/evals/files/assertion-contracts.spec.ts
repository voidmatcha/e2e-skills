import { test, expect } from '@playwright/test';

test('raw receipt text preserves spaces', async ({ page }) => {
  await page.goto('/receipt');
  expect(await page.getByTestId('receipt').textContent()).toBe('  paid  ');
});

test('list includes an exact label, not a substring', async ({ page }) => {
  await page.goto('/labels');
  expect(await page.locator('.label').allTextContents()).toContain('paid');
});

test('either supported status is visible, including when both exist', async ({ page }) => {
  await page.goto('/status');
  const a = page.getByTestId('ready');
  const b = page.getByTestId('cached');
  expect((await a.isVisible()) || (await b.isVisible())).toBe(true);
});

test('retrying exact membership already preserves the contract', async ({ page }) => {
  await page.goto('/labels');
  await expect.poll(() => page.locator('.label').allTextContents()).toContain('paid');
});

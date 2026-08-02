import { expect, test } from '@playwright/test';

test('shows the ready badge', async ({ page }) => {
  await page.goto('/dashboard');
  const visible = await page.evaluate(() => !!document.querySelector('.ready'));
  expect(visible).toBe(true);
});

test('waits for the overlay transition to finish', async ({ page }) => {
  await page.waitForFunction(() => {
    const panel = document.querySelector('.panel');
    const overlay = document.querySelector('.overlay');
    return panel && getComputedStyle(panel).opacity === '1' && overlay === null;
  });
});

test('waits for the virtualized child relationship', async ({ page }) => {
  await page.waitForFunction(
    () => document.querySelector('.virtual-list')?.children.length === 20,
  );
});

test('reads a cross-element relationship with documented intent', async ({ page }) => {
  // JUSTIFIED: no locator assertion expresses identity of these two DOM owners.
  await page.evaluate(
    () => document.querySelector('.source') === document.querySelector('.owner'),
  );
});

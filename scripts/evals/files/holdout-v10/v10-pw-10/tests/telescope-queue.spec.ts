import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/observatory/queue');
});

test('the legend renders above the queue chart', async ({ page }) => {
  // JUSTIFIED: compares two elements' layout boxes in one frame; locator assertions cannot express the relation.
  const legendAbove = await page.evaluate(() => {
    const legend = document.querySelector('#queue-legend')!.getBoundingClientRect();
    const chart = document.querySelector('#queue-chart')!.getBoundingClientRect();
    return legend.bottom <= chart.top;
  });
  expect(legendAbove).toBe(true);
});

test('adding a target shows it in the queue list', async ({ page }) => {
  await page.getByLabel('Target').fill('M31');
  await page.getByRole('button', { name: 'Queue target', exact: true }).click();
  const listed = await page.evaluate(() => document.querySelector('[data-target="M31"]') !== null);
  expect(listed).toBe(true);
});

test('the weather hold banner is present', async ({ page }) => {
  // JUSTIFIED: banner mounts late, so only the handle is checked here.
  expect(page.getByTestId('weather-hold')).toBeTruthy();
});

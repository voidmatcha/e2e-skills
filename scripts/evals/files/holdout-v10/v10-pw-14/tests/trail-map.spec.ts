import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/trails/ridge-loop/map');
});

test('closing the elevation panel hides it', async ({ page }) => {
  const panel = page.getByRole('region', { name: 'Elevation profile' });
  await expect(panel).toBeVisible();
  await page.getByRole('button', { name: 'Close elevation profile', exact: true }).click();
  await expect(panel).toBeHidden();
});

test('the only trailhead pin opens its details', async ({ page }) => {
  const pins = page.getByTestId('trailhead-pin');
  await expect(pins).toHaveCount(1);
  await pins.first().click();
  await expect(page.getByRole('heading', { name: 'Ridge Loop Trailhead' })).toBeVisible();
});

test('distance readout settles after the route loads', async ({ page }) => {
  const readout = page.getByTestId('route-distance');
  await expect.poll(async () => (await readout.textContent())?.trim()).toBe('11.4 km');
});

test('offline tiles download on supported browsers', async ({ page, browserName }) => {
  test.skip(browserName === 'webkit', 'WebKit lacks the Cache Storage quota API used for tiles');
  await page.getByRole('button', { name: 'Download offline tiles', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Tiles ready offline');
});

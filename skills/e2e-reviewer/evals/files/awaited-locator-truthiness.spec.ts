import { expect, test } from '@playwright/test';

test('earlier route', async ({ page }) => {
  const locator = page.getByText('Messaging');
  await expect(locator).toBeVisible();
});

test('bookings route', async ({ page }) => {
  const locator = page.getByTestId('horizontal-tab-upcoming');
  await expect(locator).toBeDefined();
  const loaded = true;
  await expect(loaded).toBeDefined();
});

test('local non-Locator binding', async () => {
  const locator = { loaded: true };
  await expect(locator).toBeDefined();
});

test('awaited scalar query result', async ({ page }) => {
  await expect(await page.getByText('Messaging').count()).toBeTruthy();
});

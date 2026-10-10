import { test, expect } from '@playwright/test';
test('every beacon reading is healthy', async ({ page }) => {
  await page.goto('/beacons');
  for (const reading of await page.getByTestId('beacon-reading').all()) {
    await expect(reading).toHaveText('Healthy');
  }
});

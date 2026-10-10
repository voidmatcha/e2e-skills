import { test } from '@playwright/test';
import { verifyNorth } from './support/compass';
test('shows north bearing', async ({ page }) => {
  await page.goto('/compass');
  await verifyNorth(page);
});

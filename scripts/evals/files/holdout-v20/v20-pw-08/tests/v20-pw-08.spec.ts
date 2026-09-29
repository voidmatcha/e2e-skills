import { test, expect } from '@playwright/test';

test('shows train platform and departure time', async ({ page }) => {
  await page.goto('/departures');
  await expect(page.getByTestId('platform')).toHaveText('Platform 4');
});

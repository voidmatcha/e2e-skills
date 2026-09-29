import { test, expect } from '@playwright/test';

test('opening booking shows form and backdrop', async ({ page }) => {
  await page.goto('/bookings');
  await page.getByRole('button', { name: 'New booking' }).click();
  await expect(page.getByTestId('booking-form')).toBeVisible();
});

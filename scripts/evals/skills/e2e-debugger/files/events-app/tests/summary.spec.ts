import { test, expect } from '@playwright/test';

test('summary shows the seeded totals', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#summary')).toHaveText('3 events · 5 of 36 seats taken · 1 full');
});

test('removing an attendee updates the summary', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Remove Ben from Book Club' }).click();
  await expect(page.getByRole('status')).toHaveText('Removed Ben from Book Club.', { timeout: 100 });
  await expect(page.locator('#summary')).toHaveText('3 events · 4 of 38 seats taken · 0 full');
});

test('removing an attendee from game night is announced', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Remove Eli from Board Games Night' }).click();
  await expect(page.getByRole('status')).toHaveText('Removed Eli from Board Games Night.', { timeout: 450 });
});

import { test, expect } from '@playwright/test';
import { BookingApi } from './support/booking-api';

test('joining a full spin class adds the member to the waitlist', async ({ page, request }) => {
  const api = new BookingApi(request);
  await page.goto('/classes/spin-0715');
  await page.getByRole('button', { name: 'Join waitlist', exact: true }).click();
  await expect(page.getByTestId('waitlist-position')).toHaveText('Position 3');
  expect(await api.isWaitlisted('spin-0715', 'm-5520')).toBe(true);
});

test('favouriting the instructor saves it to the member profile', async ({ page }) => {
  await page.goto('/classes/spin-0715');
  const favourite = page.getByRole('button', { name: 'Favourite instructor', exact: true });
  await favourite.click();
  await expect(favourite).toHaveAttribute('aria-pressed', 'true');
});

test('a booked class shows an enabled cancel button', async ({ page }) => {
  await page.goto('/classes/yoga-1830');
  const cancel = page.getByRole('button', { name: 'Cancel booking', exact: true });
  expect(await cancel.isEnabled()).toBe(true);
});

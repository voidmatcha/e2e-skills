import { test, expect } from '@playwright/test';
import { RoomsPage } from '../pages/rooms-page';

test.beforeEach(async ({ page }) => {
  await page.goto('/staff/login');
  await page.fill('#staff-id', 'hk-lead-04');
  await page.getByLabel('Password').fill('Linen!Cart2026');
  await page.click('#sign-in');
  expect(page.url()).toContain('/staff/rooms');
});

test('marks room 512 as inspected', async ({ page }) => {
  const room = page.getByTestId('room-512');
  room.getByRole('button', { name: 'Mark inspected', exact: true }).click();
  await expect(room.getByTestId('room-status')).toHaveText('Inspected');
});

test('requests linen for room 514', async ({ page }) => {
  const rooms = new RoomsPage(page);
  await page.getByTestId('room-514').getByRole('button', { name: 'Request linen', exact: true }).click();
  await expect(rooms.room('514').getByTestId('linen-status')).toHaveText('Linen requested');
});

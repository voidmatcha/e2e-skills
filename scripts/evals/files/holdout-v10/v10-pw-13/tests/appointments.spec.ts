import { test, expect } from '@playwright/test';
import { newChartNumber } from './support/patients';

test.describe.serial('appointment booking', () => {
  test('books a follow-up with Dr. Amani', async ({ page }) => {
    await page.goto(`/clinic/patients/${newChartNumber()}/book`);
    await page.waitForLoadState('networkidle', { timeout: 15_000 });
    await page.getByRole('option', { name: 'Dr. Amani', exact: true }).click();
    await page.getByRole('button', { name: 'Book follow-up', exact: true }).click();
    await expect(page.getByRole('status')).toHaveText('Follow-up booked for 9 Oct, 10:30');
  });

  test.skip('reschedules the follow-up to the afternoon', async ({ page }) => {
    await page.goto('/clinic/appointments');
    await page.getByRole('button', { name: 'Reschedule', exact: true }).click();
    await expect(page.getByRole('status')).toHaveText('Moved to 9 Oct, 15:00');
  });
});

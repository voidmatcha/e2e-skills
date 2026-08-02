import { expect, test } from '@playwright/test';
import { ReportPage } from '../pages/report-page';

test('exports a receipt and reaches its route', async ({ page }) => {
  const report = new ReportPage(page);
  await report.open();
  await report.waitUntilReady();
  await report.exportReceipt();
  expect(new URL(page.url()).pathname).toBe('/receipts/latest');
});

test('retries the receipt route until navigation settles', async ({ page }) => {
  const report = new ReportPage(page);
  await report.open();
  await report.exportReceipt();
  await expect(async () => {
    expect(new URL(page.url()).pathname).toBe('/receipts/latest');
  }).toPass();
});

test('opens the tutorial-covered menu intentionally', async ({ page }) => {
  const report = new ReportPage(page);
  await report.open();
  await report.openCoveredMenu();
  await expect(page.getByRole('menu')).toBeVisible();
});

test.afterEach(async ({ page }) => {
  await page.close().catch((error) => {
    throw error;
  });
});

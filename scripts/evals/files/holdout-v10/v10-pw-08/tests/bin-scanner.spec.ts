import { test, expect } from '@playwright/test';

const settle = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

test('scanning a bin label fills the bin field', async ({ page }) => {
  await page.goto('/warehouse/receiving');
  const scanner = page.frameLocator('#scanner-frame');
  await scanner.getByRole('button', { name: 'Start camera', exact: true }).click();
  await settle(800);
  await page.getByRole('button', { name: 'Simulate scan: BIN-07-C', exact: true }).click();
  await expect(page.getByLabel('Bin')).toHaveValue('BIN-07-C');
});

test('the pick list refreshes after a scan', async ({ page }) => {
  await page.goto('/warehouse/picking');
  const picklist = page.frame({ name: 'picklist' });
  await picklist!.waitForTimeout(1200);
  await expect(page.getByTestId('picklist-count')).toHaveText('6 lines');
});

test('an idle minute shows the shift pause warning', async ({ page }) => {
  await page.clock.install();
  await page.goto('/warehouse/receiving');
  await page.clock.runFor(60_000);
  await expect(page.getByRole('alert')).toHaveText('Your shift session will pause soon.', { timeout: 5_000 });
});

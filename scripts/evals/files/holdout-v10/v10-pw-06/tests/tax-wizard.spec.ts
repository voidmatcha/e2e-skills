import { test, expect } from '@playwright/test';

test('fills the income step and reaches deductions', async ({ page }) => {
  await page.goto('/returns/2025/wizard');
  const income = page.getByRole('form', { name: 'Income' });
  await expect.soft(income).toBeVisible();
  await income.getByLabel('Gross salary').fill('58200');
  await income.getByRole('button', { name: 'Continue', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Deductions' })).toBeVisible();
});

test('summary lists the filer details', async ({ page }) => {
  await page.goto('/returns/2025/summary');
  await expect(page.getByRole('heading', { name: 'Return summary' })).toBeVisible();
  await expect.soft(page.getByTestId('filer-name')).toHaveText('Dana Okafor');
  await expect.soft(page.getByTestId('filer-tin')).toHaveText('***-**-4471');
  await expect.soft(page.getByTestId('filing-status')).toHaveText('Single');
});

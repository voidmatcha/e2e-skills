import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/classes/bio-201/gradebook');
});

test('exports the gradebook as CSV', async ({ page }) => {
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export CSV', exact: true }).click(),
  ]);
  expect(download.suggestedFilename()).toBe('bio-201-gradebook.csv');
});

test('late penalty recalculates the average', async ({ page }) => {
  await page.getByLabel('Late penalty (%)').fill('10');
  await expect(async () => {
    expect(await page.getByTestId('class-average').textContent()).toBe('78.4');
  }).toPass({ timeout: 5_000 });
});

test('print view preloads the rubric stylesheet', async ({ page }) => {
  await page.getByRole('button', { name: 'Print view', exact: true }).click();
  await expect(page.locator('link[rel="preload"][href$="rubric-print.css"]')).toBeAttached();
});

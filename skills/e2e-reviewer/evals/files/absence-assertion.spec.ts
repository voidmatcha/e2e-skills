import { test, expect } from '@playwright/test';

test.describe('job runner', () => {
  test('cancel stops the running job', async ({ page }) => {
    await page.goto('/jobs/42');
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    // BAD (#4i) — '.spinner' appears nowhere else in this test and nothing positive is
    // asserted alongside, so a rotted selector keeps this green without observing the cancel.
    await expect(page.locator('.job-controls .spinner')).not.toBeVisible();
  });

  test('spinner clears after the job finishes', async ({ page }) => {
    await page.goto('/jobs/43');
    const spinner = page.getByTestId('run-spinner');
    // GOOD — the same locator is proven able to match before absence is asserted
    await expect(spinner).toBeVisible();
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(spinner).toBeHidden();
  });

  test('empty search shows the empty state', async ({ page }) => {
    await page.goto('/jobs?q=nonexistent');
    // GOOD — empty-state case with a positive counterpart asserted alongside
    await expect(page.getByText('No jobs match your search')).toBeVisible();
    await expect(page.getByTestId('job-row')).toHaveCount(0);
  });

  test('archived jobs are removed from the active list', async ({ page }) => {
    await page.goto('/jobs/44');
    const row = page.getByTestId('active-job-row');
    await row.click();
    await page.getByRole('button', { name: 'Archive', exact: true }).click();
    // GOOD — the locator was the target of an action earlier in this test
    await expect(row).toHaveCount(0);
  });
});

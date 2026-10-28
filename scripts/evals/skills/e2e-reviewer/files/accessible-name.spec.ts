import { test, expect } from '@playwright/test';

// A jobs dashboard that renders user/data-controlled list text — row titles like
// "Job Application", "Jobs Board", "New Job" all contain the word "Job", so an
// unscoped getByRole name:'Job' substring-matches multiple elements (strict-mode).
test.describe('jobs dashboard navigation', () => {
  test('open the Job detail from the sidebar', async ({ page }) => {
    await page.goto('/dashboard');
    // BAD (#10c) — unscoped, no exact: 'Job' substring-collides with dynamic row titles
    await page.getByRole('link', { name: 'Job' }).click();
    await expect(page.getByTestId('job-detail-heading')).toBeVisible();
  });

  test('scoped and exact variants are safe', async ({ page }) => {
    await page.goto('/dashboard');
    // GOOD — scoped to a container locator: the match is bounded to the sidebar subtree
    await page.locator('[data-testid="sidebar"]').getByRole('link', { name: 'Job' }).click();
    // GOOD — exact: true: no substring collision possible
    await page.getByRole('button', { name: 'Submit', exact: true }).click();
    // GOOD — distinctive multi-word name unlikely to appear as a substring in dynamic text
    await page.getByRole('link', { name: 'Download Annual Report 2025' }).click();
    await expect(page).toHaveURL(/report/);
  });
});

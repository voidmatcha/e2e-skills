import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/volunteer/shifts');
});

test('switches the board to the weekend view', async ({ page }) => {
  await page.getByRole('tab', { name: 'Weekend' }).click();
  await expect(page.getByRole('tabpanel', { name: 'Weekend' })).toBeVisible();
});

test('the shift toolbar offers an Export week button', async ({ page }) => {
  await expect(page.getByTestId('shift-toolbar')).toMatchAriaSnapshot(`
    - button "Print week"
    - button
  `);
});

test('opens the printable roster from the header', async ({ page }) => {
  await page.getByRole('link', { name: 'Roster' }).click();
  await expect(page).toHaveURL(/\/volunteer\/roster$/);
});

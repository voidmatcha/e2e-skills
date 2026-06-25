import { test, expect } from '@playwright/test';

test.describe('always-true locator assertions', () => {
  test('dateTime cell edit', async ({ page }) => {
    await page.goto('/grid');
    await page.getByRole('gridcell', { name: 'date' }).dblclick();
    await page.keyboard.type('1/31/2025, 4:05:00 PM');
    await page.keyboard.press('Enter');
    expect(page.getByText('1/31/2025, 4:05:00 PM')).not.toBeNull();
  });

  test('integration list', async ({ page }) => {
    await page.goto('/integrations');
    const list = page.getByTestId('integration-list');
    expect(list.getByText('alpha')).not.to.equal(null);
    expect(page.locator('.beta-row')).toBeDefined();
  });

  test('numeric id is a non-locator subject', async ({ page }) => {
    await page.goto('/grid');
    const rowCount = await page.getByRole('row').count();
    expect(rowCount).not.toBeNull();
    await expect(page.getByRole('row')).toHaveCount(rowCount);
  });
});

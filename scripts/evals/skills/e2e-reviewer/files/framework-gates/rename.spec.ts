import { test, expect } from '@playwright/test';

test.describe('framework keys', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/keys');
    await expect(page.getByTestId('key-list')).toBeVisible();
  });

  test('renames the selected key', async ({ page }) => {
    const target = page.getByTestId('rename-target');
    await page.getByTestId('rename-button').click();

    await expect(target).toHaveAttribute('data-key', 'renamed');
    const label = await target.getAttribute('aria-label');
    if (label) expect(label).toContain('renamed');
  });
});

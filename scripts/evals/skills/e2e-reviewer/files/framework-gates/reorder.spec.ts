import { test, expect } from '@playwright/test';

test.describe('framework keys', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/keys');
    await expect(page.getByTestId('key-list')).toBeVisible();
  });

  test('keeps the selected key stable through reorder', async ({ page }) => {
    const target = page.getByTestId('reorder-target');
    const keyBefore = await target.getAttribute('data-key');
    expect(keyBefore).not.toBeNull();

    await page.getByTestId('reorder-button').click();

    const keyAfter = await target.getAttribute('data-key');
    if (keyAfter) expect(keyAfter).toBe(keyBefore);
    await expect(target).not.toHaveAttribute('data-key', 'c');
  });
});

import { test, expect } from '@playwright/test';
import { MineralShelf } from '../pages/MineralShelf';
test('shows quartz specimen', async ({ page }) => {
  await page.goto('/minerals');
  const shelf = new MineralShelf(page);
  await expect(shelf.specimen()).toContainText('Quartz');
  await expect(page.getByTestId('certificate')).toHaveCount(1);
  await expect(shelf.onlyCertificate()).toBeVisible();
});

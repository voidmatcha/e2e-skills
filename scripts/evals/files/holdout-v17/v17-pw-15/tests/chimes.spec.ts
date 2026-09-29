import { test, expect } from '@playwright/test';
test('names the wind chime control', async ({ page }) => {
  await page.goto('/chimes');
  await expect(page.getByTestId('panel')).toMatchAriaSnapshot(`- button`);
});
test('all chimes are tuned', async ({ page }) => {
  await page.goto('/chimes');
  for (const chime of await page.getByTestId('chime').all()) {
    await expect(chime).toHaveAttribute('data-tuned', 'true');
  }
});

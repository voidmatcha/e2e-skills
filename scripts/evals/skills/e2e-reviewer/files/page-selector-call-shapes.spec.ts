import { test } from '@playwright/test';

test('selector call shapes', async ({ page }) => {
  const widget = { click(_options: { timeout: number }) {}, type(_value: string) {} };
  await page.click('#save');
  widget.click({ timeout: 1000 });
  widget.type('value');
});

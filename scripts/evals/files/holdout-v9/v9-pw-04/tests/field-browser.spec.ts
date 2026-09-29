import { test, expect } from '@playwright/test';
import { FieldBrowser } from '../pages/field-browser';

test('opens the top values popover for the host field', async ({ page }) => {
  const browser = new FieldBrowser(page);
  await browser.open();
  await browser.showTopValues('host.name');
  await expect(browser.topValuesHeader()).toHaveText('Top 5 values of host.name');
});

test('shows the keyword type for the host field', async ({ page }) => {
  const browser = new FieldBrowser(page);
  await browser.open();
  await expect(page.getByTestId('field-row').nth(2)).toHaveText('host.name: keyword');
});

// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';

test('catalog excludes disabled entries after loading', async ({ page }) => {
  await page.route('**/api/entries', route => route.fulfill({ json: [
    { code: 'handbook', label: 'Handbook', enabled: true },
    { code: 'obsolete', label: 'Obsolete guide', enabled: false },
  ] }));
  await page.goto('/catalog');
  await expect(page.getByRole('status')).toHaveText('Catalog loaded');
  await expect(page.getByTestId('entry-handbook')).toHaveText('Handbook');
  await expect(page.getByTestId('entry-obsolete')).toHaveCount(0);
});

test('dismisses the catalog hint', async ({ page }) => {
  await page.goto('/catalog');
  await page.getByRole('button', { name: 'Dismiss hint', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Catalog', exact: true })).toBeVisible();
  await expect(page.locator('.retired-hint')).toHaveCount(0);
});

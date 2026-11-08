// SPDX-License-Identifier: Apache-2.0
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('account menu has no accessibility violations', async ({ page }) => {
  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'Account' }).click();
  await page.getByRole('menuitem').first().waitFor({ state: 'visible' }).catch(() => undefined);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

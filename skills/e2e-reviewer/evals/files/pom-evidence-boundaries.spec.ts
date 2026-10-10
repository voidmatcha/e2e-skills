import { expect, test } from '@playwright/test';
import { CatalogPage } from './pages/catalog-page';
import { DisplayPreferencesPage } from './pages/display-preferences-page';

test('archives the current catalog item', async ({ page }) => {
  const catalog = new CatalogPage(page);
  await catalog.open();
  await page.getByRole('button', { name: 'Accept optional cookies' }).click();
  await page.getByRole('button', { name: 'Archive item' }).click();
  await page.getByRole('button', { name: 'Confirm archive' }).click();
  await expect(page.getByRole('status')).toHaveText('Archived');
});

test('changes display density through a navigation-only POM', async ({ page }) => {
  const preferences = new DisplayPreferencesPage(page);
  await preferences.open();
  await page.getByLabel('Display density').selectOption('compact');
  await expect(page.getByLabel('Display density')).toHaveValue('compact');
});

test('starts an import on a nearby route outside the catalog POM', async ({ page }) => {
  const catalog = new CatalogPage(page);
  await catalog.open();
  await page.goto('/catalog/imports');
  await page.getByRole('button', { name: 'Start import' }).click();
  await expect(page.getByRole('status')).toHaveText('Import started');
});

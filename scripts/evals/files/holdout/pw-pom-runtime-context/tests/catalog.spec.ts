import { expect, type Page, test } from '@playwright/test';
import { CatalogPage } from '../pages/catalog-page';
import { nextSequence } from '../support/sequence';

let page: Page;

test.beforeEach(async ({ page: fixturePage }) => {
  page = fixturePage;
  await page.goto('/catalog');
});

test.afterEach(async () => {
  try {
    await page.evaluate(() => localStorage.removeItem('catalog-seed'));
  } catch {
    // Optional teardown must not hide the test result.
  }
});

test('opens catalog help and renders the catalog root', async () => {
  const catalog = new CatalogPage(page);
  await catalog.waitUntilSettled();
  await catalog.openBrowserHelp();

  expect(await catalog.hasCatalogRoot()).toBe(true);
  expect(await catalog.readDirection()).toBe('ltr');
  expect(nextSequence()).toBeGreaterThan(0);
  await expect(
    page.getByRole('dialog', { name: 'Catalog help', exact: true }),
  ).toBeVisible();
  await expect(catalog.heading).toHaveText('Catalog');
});

test('keeps the catalog heading after using help controls', async () => {
  const catalog = new CatalogPage(page);
  await catalog.waitUntilSettled();
  await catalog.openBrowserHelp();
  await catalog.closeBrowserHelp();

  expect(await catalog.hasCatalogRoot()).toBe(true);
  expect(await catalog.readDirection()).toBe('ltr');
  expect(nextSequence()).toBeGreaterThan(0);
  await expect(catalog.heading).toHaveText('Catalog');
});

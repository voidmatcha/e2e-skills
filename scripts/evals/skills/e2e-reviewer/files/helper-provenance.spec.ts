import { test, expect, type Page } from '@playwright/test';

const nameField = (page: Page) => page.getByLabel('Name');
function row(page: Page, name: string) {
  return page.locator('#list li').filter({ has: page.getByRole('heading', { name, exact: true }) });
}
async function addItem(page: Page, name: string) {
  await nameField(page).fill(name);
  await page.getByRole('button', { name: 'Add', exact: true }).click();
}

test('adds items through same-file helpers', async ({ page }) => {
  await page.goto('/items');
  await addItem(page, 'Alpha');
  await expect(row(page, 'Alpha')).toBeVisible();
  for (const heading of ['Items', 'Recent']) {
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
  }
});

test('checks a row through a helper with a truthiness matcher', async ({ page }) => {
  await page.goto('/items');
  expect(row(page, 'Beta')).toBeTruthy();
});

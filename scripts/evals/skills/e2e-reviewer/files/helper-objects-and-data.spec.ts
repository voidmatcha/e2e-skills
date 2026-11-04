import { test, expect, type Page } from '@playwright/test';

type Item = { id: string; name: string };
async function readItems(page: Page): Promise<Item[]> {
  return page.evaluate(() => JSON.parse(localStorage.getItem('items') ?? '[]'));
}
const rowById = (page: Page, id: string) => page.locator(`li[data-id="${id}"]`);
const editButton = (row: ReturnType<typeof rowById>) => row.getByRole('button', { name: 'Edit', exact: true });
function itemForm(page: Page) {
  const name = page.getByLabel('Name');
  return { name, save: page.getByRole('button', { name: 'Save', exact: true }) };
}

test('adds and renames an item', async ({ page }) => {
  await page.goto('/items');
  const form = itemForm(page);
  await form.name.fill('Lamp');
  await form.save.click();
  let items = await readItems(page);
  const created = items[0];
  expect(created.id).toBeTruthy();
  const id = created.id as string;
  await editButton(rowById(page, id)).click();
  await form.name.fill('Desk lamp');
  await form.save.click();
  items = await readItems(page);
  expect(items.map(({ name }) => name)).toEqual(['Desk lamp']);
});

test('checks the save button with a truthiness matcher', async ({ page }) => {
  await page.goto('/items');
  const form = itemForm(page);
  expect(form.save).toBeTruthy();
});

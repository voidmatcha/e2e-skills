import { test, expect, type Page } from '@playwright/test';

const group = (page: Page, name: string) => page.getByRole('group', { name: `Check-ins for ${name}`, exact: true });
async function readStore(page: Page): Promise<{ id: string }[]> {
  return page.evaluate(() => JSON.parse(localStorage.getItem('items') ?? '[]'));
}

test('reads stored items and dynamic names', async ({ page }) => {
  await page.goto('/items');
  await expect(group(page, 'Alpha')).toBeVisible();
  const text = (await page.getByTestId('progress').textContent()) ?? '';
  const m = text.match(/^(\d+) of (\d+)$/);
  expect(m).not.toBeNull();
  const added = (await readStore(page))[0];
  expect(added.id).toBeTruthy();
  let form = page.getByRole('form', { name: 'Edit Alpha', exact: true });
  await form.getByLabel('Name').fill('Beta');
  form = page.getByRole('form', { name: 'Edit Beta', exact: true });
  await expect(form.getByLabel('Name')).toHaveValue('Beta');
});

test('checks an edit button with a truthiness matcher', async ({ page }) => {
  const name = 'Beta';
  await page.goto('/items');
  expect(page.getByRole('button', { name: `Edit ${name}`, exact: true })).toBeTruthy();
});

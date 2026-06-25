import { test, expect } from '@playwright/test';

// TRUE POSITIVE — #2 Missing Then (P0): performs a real entity delete but never
// asserts the entity is gone. The delete could no-op and this test stays green.
test('Delete the workspace', async ({ page }) => {
  await page.goto('/workspaces/demo');
  await expect(page.getByRole('heading', { name: 'Workspace settings' })).toBeVisible();
  await page.getByRole('button', { name: 'Delete workspace' }).click();
  await page.getByLabel('Type the workspace name to confirm').fill('demo');
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  // no assertion that the workspace row / page is gone
});

// FALSE POSITIVE — API/request delete whose negative assertion is a 404 GET.
test('API delete then 404 confirms removal', async ({ playwright }) => {
  const api = await playwright.request.newContext();
  await api.delete('/api/leases/42');
  const after = await api.get('/api/leases/42');
  expect(after.status()).toBe(404);
});

// FALSE POSITIVE — cleanup/teardown delete; verification is not its job.
test.afterEach(async ({ page }) => {
  await page.getByRole('button', { name: 'Delete test fixture' }).click();
});

// FALSE POSITIVE — success-toast confirmation counts as verifying the delete.
test('should delete a profile', async ({ page }) => {
  await page.goto('/profiles/7');
  await page.getByRole('button', { name: 'Delete profile' }).click();
  await expect(page.getByText(/profile deleted/i)).toBeVisible();
});

// FALSE POSITIVE — non-entity "remove" (editor text), not a deletion of a record.
test('should remove selected text from the editor', async ({ page }) => {
  await page.goto('/editor');
  await page.getByRole('textbox').selectText();
  await page.keyboard.press('Delete');
  await expect(page.getByRole('textbox')).toBeEmpty();
});

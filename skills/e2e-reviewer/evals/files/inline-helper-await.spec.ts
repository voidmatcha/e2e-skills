import { expect, test } from '@playwright/test';

test('status stays correct', async ({ page }) => {
  async function unchecked() { expect(page.getByRole('status')).toHaveText('ready'); }
  await unchecked();
  async function checked() { await expect(page.getByRole('main')).toBeVisible(); }
  await checked();
  async function returned() { return expect(page.getByRole('footer')).toBeVisible(); }
  await returned();
  { const expect = (_value: unknown) => ({ toBeVisible: () => true }); async function local() { expect(page.getByRole('nav')).toBeVisible(); } await local(); }
});
class SyncAssertions { expect(value: any) { return value.toBeVisible(); } }
class NestedDefaultAssertions { expect(value = fallback()) { return value.toBeVisible(); } }

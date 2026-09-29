import { test, expect } from '@playwright/test';

const SETTLED = 'networkidle';

test('shows the synced badge after a manual sync', async ({ page }) => {
  await page.route('**/api/sync', (route) => route.fulfill({ status: 200, body: '{"ok":true}' }));
  await page.goto('/workspaces/sync');
  await page.getByRole('button', { name: 'Sync now', exact: true }).click();
  await expect(async () => {
    expect(await page.getByTestId('sync-badge').textContent()).toBe('Synced');
  }).toPass({ timeout: 10_000 });
});

test('shows the last sync timestamp', async ({ page }) => {
  await page.goto('/workspaces/sync');
  await page.waitForLoadState(SETTLED);
  await expect(page.getByTestId('last-sync')).toContainText('Last synced');
});

test('lists every synced workspace', async ({ page }) => {
  await page.goto('/workspaces/sync');
  const rows = await page.getByTestId('workspace-row').count();
  expect(rows).toBeGreaterThan(-1);
});

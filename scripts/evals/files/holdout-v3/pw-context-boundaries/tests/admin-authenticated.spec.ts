import { expect, test } from '@playwright/test';
import { ReleaseChannel } from '../support/release-channel';

test('shows authenticated admin navigation', async ({ page }) => {
  await page.goto('/admin/navigation');
  await expect(page.getByRole('navigation', { name: 'Admin', exact: true })).toBeVisible();
});

test('reads a browser-only computed layout contract', async ({ page }) => {
  // JUSTIFIED: computed pseudo-element content is not exposed by locators.
  const content = await page.evaluate(
    () => getComputedStyle(document.body, '::before').content,
  );
  expect(content).toContain('admin');
});

test('uses the application release filter', async () => {
  const release = new ReleaseChannel();
  expect(release.only(['stable', 'beta'], 'stable')).toEqual(['stable']);
});

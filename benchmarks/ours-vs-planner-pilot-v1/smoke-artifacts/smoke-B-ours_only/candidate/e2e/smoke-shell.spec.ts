import { test, expect, getGrid, clearAllStorage, resetViewport } from './fixtures';

test.describe('Application Shell', () => {
  test.afterEach(async ({ page }) => {
    await clearAllStorage(page);
    await resetViewport(page);
  });

  test('loads the app shell with the primary navigation visible', async ({ page }) => {
    // Given: the application is served at the configured baseURL

    // When: a user opens the root route
    await page.goto('/');

    // Then: the primary navigation landmark is rendered by the app shell.
    // No readiness helper runs first on purpose - this retrying assertion is
    // the readiness gate, so a shell that never mounts fails right here.
    const primaryNav = page.getByRole('navigation', { name: 'Tool Switcher' });
    await expect(primaryNav).toBeVisible();

    // And: it exposes the three tool tabs, with Layout active by default.
    // Asserted by accessible name, not text: the tabs render icon-only on the
    // tablet and mobile projects, where they keep aria-label but show no label.
    await expect(primaryNav.getByRole('tab')).toHaveCount(3);
    await expect(primaryNav.getByRole('tab', { name: 'Bins' })).toBeVisible();
    await expect(primaryNav.getByRole('tab', { name: 'Baseplate' })).toBeVisible();
    await expect(primaryNav.getByRole('tab', { name: 'Layout' })).toHaveAttribute(
      'aria-selected',
      'true'
    );

    // And: the surrounding shell - header banner and grid planner - is visible
    const grid = await getGrid(page);
    await expect(page.getByRole('banner')).toBeVisible();
    await expect(grid).toBeVisible();
  });
});

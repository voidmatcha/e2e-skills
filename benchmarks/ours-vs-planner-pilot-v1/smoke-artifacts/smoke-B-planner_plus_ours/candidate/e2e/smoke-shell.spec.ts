import { test, expect, waitForAppReady, clearAllStorage } from './fixtures';

/**
 * Shell smoke test: proves the app boots at `/` and renders its primary
 * navigation (the header "Tool Switcher" landmark and its Layout/Bins/Baseplate
 * tabs). Every locator below was resolved against the live page, not source.
 *
 * Note: `/` rewrites client-side to `/l/<opaque-id>/untitled-layout`, so the URL
 * is deliberately not asserted.
 */
test.describe('Application shell', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await clearAllStorage(page);
    await page.reload();
    await waitForAppReady(page);
  });

  test.afterEach(async ({ page }) => {
    await clearAllStorage(page);
  });

  test('loads at / with the primary navigation visible', async ({ page }) => {
    // Given: the app is served at the configured baseURL
    // When: a user opens `/` (handled by beforeEach)

    // Then: the application shell has loaded and the primary navigation is visible.
    // Tabs are scoped to the Tool Switcher because a second, unrelated tablist
    // (Inspector/History) exists in the right-hand panel.
    const gridRegion = page.locator('[role="application"]');
    const toolSwitcher = page.getByRole('navigation', { name: 'Tool Switcher' });
    const toolTabs = toolSwitcher.getByRole('tab');
    const layoutTab = toolSwitcher.getByRole('tab', { name: 'Layout' });

    // Settled-state gate: the shell mounted and rendered the grid region.
    await expect(gridRegion).toBeVisible();

    await expect(toolSwitcher).toBeVisible();
    await expect(toolTabs).toHaveCount(3);
    await expect(layoutTab).toHaveAttribute('aria-selected', 'true');
  });
});

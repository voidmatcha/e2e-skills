import {
  test,
  expect,
  waitForAppReady,
  drawBinOnGrid,
  getGridBounds,
  getSidebar,
  waitForBinCount,
  clearAllStorage,
  resetViewport,
} from './fixtures';

/**
 * Shrinking the drawer must recompute the baseplate grid AND report every bin
 * that no longer fits by moving it to the stash - never silently keep an
 * out-of-bounds bin on the grid.
 *
 * Displacement rule under test: src/core/store/layout/drawerActions.ts
 * (`computeDisplacedBins` -> bins reassigned to the staging layer).
 */
test.describe('Drawer resize displacement', () => {
  // Default drawer of a fresh layout, observed in the browser: 10 columns x 8 rows.
  const INITIAL_COLUMNS = 10;
  const INITIAL_ROWS = 8;
  const NARROWED_COLUMNS = 5;

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await clearAllStorage(page);
    await page.reload();
    await waitForAppReady(page);
  });

  test.afterEach(async ({ page }) => {
    await clearAllStorage(page);
    await resetViewport(page);
  });

  test('narrowing the drawer recomputes the baseplate grid and stashes the bin that no longer fits', async ({
    page,
  }) => {
    // The drawer width stepper lives in the desktop sidebar ([data-sidebar]);
    // the mobile layout surfaces drawer settings through a bottom sheet instead.
    const viewport = page.viewportSize();
    test.skip((viewport?.width ?? 0) < 900, 'desktop-only sidebar flow');

    const grid = page.locator('[role="application"]');
    const sidebar = getSidebar(page);
    const drawerWidth = sidebar.getByRole('spinbutton', { name: 'Drawer width in grid units' });
    const gridBins = page.locator('[data-bin-id]');
    const lastColumnHeader = page.getByRole('button', {
      name: `Select bins in column ${INITIAL_COLUMNS}`,
    });

    // Given: a fresh 10u x 8u drawer (420 x 336 mm on the 42mm grid)
    await expect(grid).toHaveAttribute(
      'aria-label',
      `Gridfinity drawer grid, ${INITIAL_COLUMNS} columns by ${INITIAL_ROWS} rows`
    );
    await expect(drawerWidth).toHaveValue(String(INITIAL_COLUMNS));
    await expect(sidebar.getByText('420 × 336 × 84 mm')).toBeVisible();
    await expect(lastColumnHeader).toBeVisible();

    // Given: a bin drawn in the far right column - inside the drawer today,
    // outside it once the drawer is narrowed to 5 columns.
    const bounds = await getGridBounds(page);
    const cellWidth = bounds.width / INITIAL_COLUMNS;
    const cellHeight = bounds.height / INITIAL_ROWS;
    const rightColumnX = cellWidth * 9.5;
    const leftColumnX = cellWidth * 1.5;
    const firstRowY = cellHeight * 0.5;
    const secondRowY = cellHeight * 1.5;
    await drawBinOnGrid(page, rightColumnX, firstRowY, rightColumnX, secondRowY);
    await waitForBinCount(page, 1);
    const displacedBinId = await gridBins.getAttribute('data-bin-id');

    // Given: a second bin in column 2, which still fits after the resize.
    await drawBinOnGrid(page, leftColumnX, firstRowY, leftColumnX, secondRowY);
    await waitForBinCount(page, 2);
    await expect(page.locator('[data-staging-bin-id]')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Stash 1 bins' })).toBeHidden();

    // When: the user narrows the drawer from 10 to 5 grid units
    await drawerWidth.fill(String(NARROWED_COLUMNS));
    await drawerWidth.blur();

    // Then: the baseplate grid is recomputed to the new drawer footprint
    await expect(grid).toHaveAttribute(
      'aria-label',
      `Gridfinity drawer grid, ${NARROWED_COLUMNS} columns by ${INITIAL_ROWS} rows`
    );
    await expect(sidebar.getByText('210 × 336 × 84 mm')).toBeVisible();
    await expect(lastColumnHeader).toBeHidden();

    // Then: the bin that no longer fits is reported in the stash, not silently
    // kept on the grid - same bin id, moved from the grid to the stash.
    await expect(page.locator(`[data-staging-bin-id="${displacedBinId}"]`)).toHaveCount(1);
    await expect(page.locator(`[data-bin-id="${displacedBinId}"]`)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Stash 1 bins' })).toBeVisible();

    // Then: the bin that still fits is left alone on the grid
    await expect(gridBins).toHaveCount(1);
  });
});

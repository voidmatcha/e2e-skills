import {
  test,
  expect,
  waitForAppReady,
  waitForBinCount,
  waitForStagingBinCount,
  getGridBounds,
  getSidebar,
  getNewestBin,
  clearAllStorage,
  resetViewport,
} from './fixtures';

/**
 * Resizing the drawer re-derives the baseplate grid. A bin whose footprint no
 * longer fits the smaller drawer must be reported to the user — the app moves
 * it into the Stash and shows a stash count — instead of being silently kept
 * on a grid it no longer fits (see `computeDisplacedBins`).
 */
const GRID_LABEL = 'Gridfinity drawer grid';

test.describe('Drawer resize vs. bins that no longer fit', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);
    await clearAllStorage(page);
    await page.reload();
    await waitForAppReady(page);
  });

  test.afterEach(async ({ page }) => {
    await clearAllStorage(page);
    await resetViewport(page);
  });

  test('shrinking drawer width recomputes the grid and stashes the bin that no longer fits', async ({
    page,
  }) => {
    const grid = page.getByRole('application', { name: new RegExp(`^${GRID_LABEL},`) });
    const widthField = page.getByRole('spinbutton', { name: 'Drawer width in grid units' });
    const depthField = page.getByRole('spinbutton', { name: 'Drawer depth in grid units' });
    const decreaseWidth = getSidebar(page).getByRole('button', {
      name: 'Decrease Drawer width in grid units',
    });
    const stashCount = page.getByRole('button', { name: /^Stash \d+ bins?$/ });

    const columns = Number(await widthField.inputValue());
    const rows = Number(await depthField.inputValue());
    expect(columns).toBeGreaterThan(1);
    await expect(grid).toHaveAttribute('aria-label', `${GRID_LABEL}, ${columns} columns by ${rows} rows`);

    /**
     * Draw a bin by dragging between two grid-cell coordinates. Cell size is
     * derived from the live grid bounds because the app auto-zooms the grid to
     * fit the viewport.
     */
    const drawBinBetweenCells = async (x1: number, y1: number, x2: number, y2: number) => {
      const before = await page.locator('[data-bin-id]').count();
      const bounds = await getGridBounds(page);
      const cellWidth = bounds.width / columns;
      const cellHeight = bounds.height / rows;
      await page.mouse.move(bounds.x + x1 * cellWidth, bounds.y + y1 * cellHeight);
      await page.mouse.down();
      await page.mouse.move(bounds.x + x2 * cellWidth, bounds.y + y2 * cellHeight, { steps: 5 });
      await page.mouse.up();
      await waitForBinCount(page, before + 1);
      return getNewestBin(page);
    };

    // A bin in the first column — it still fits after the drawer loses its last column.
    const keptBin = await drawBinBetweenCells(0.2, 0.2, 0.8, 0.8);
    const keptBinId = await keptBin.getAttribute('data-bin-id');

    // A bin straddling the last column — it cannot fit once that column is gone.
    const edgeBin = await drawBinBetweenCells(columns - 1.4, 3.2, columns - 0.05, 3.8);
    const edgeBinId = await edgeBin.getAttribute('data-bin-id');

    expect(keptBinId).toBeTruthy();
    expect(edgeBinId).toBeTruthy();
    expect(edgeBinId).not.toBe(keptBinId);

    // Settled pre-state: both bins are on the grid and nothing is stashed yet.
    await waitForBinCount(page, 2);
    await waitForStagingBinCount(page, 0);
    await expect(stashCount).toHaveCount(0);

    await decreaseWidth.click();

    // The baseplate grid is recomputed to the new drawer width.
    await expect(widthField).toHaveValue(String(columns - 1));
    await expect(grid).toHaveAttribute(
      'aria-label',
      `${GRID_LABEL}, ${columns - 1} columns by ${rows} rows`
    );

    // PRIMARY OUTCOME: the bin that no longer fits is reported in the Stash —
    // the same bin, identified by id — rather than silently kept on the grid.
    await expect(page.locator(`[data-staging-bin-id="${edgeBinId}"]`)).toBeVisible();
    await expect(page.locator(`[data-bin-id="${edgeBinId}"]`)).toHaveCount(0);
    await expect(stashCount).toHaveText(/1 bins?/);

    // The bin that still fits is untouched, so displacement is selective.
    await expect(page.locator(`[data-bin-id="${keptBinId}"]`)).toBeVisible();
    await waitForBinCount(page, 1);
  });
});

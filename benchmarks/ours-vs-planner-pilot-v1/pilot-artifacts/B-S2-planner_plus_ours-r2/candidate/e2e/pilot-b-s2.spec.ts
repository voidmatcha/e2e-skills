import {
  test,
  expect,
  waitForAppReady,
  getGridBounds,
  drawBinOnGrid,
  getSidebar,
  getStash,
  clearAllStorage,
  resetViewport,
} from './fixtures';

// Default drawer on a fresh profile: 10 columns x 8 rows (observed on the live app).
const DEFAULT_COLUMNS = 10;
const DEFAULT_ROWS = 8;

test.describe('Drawer resize', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);
  });

  test.afterEach(async ({ page }) => {
    await clearAllStorage(page);
    await resetViewport(page);
  });

  test('shrinking drawer width recomputes the grid and reports the bin that no longer fits', async ({
    page,
  }) => {
    const grid = page.locator('[role="application"]');
    const sidebar = getSidebar(page);
    const stash = getStash(page);
    const widthInput = sidebar.getByRole('spinbutton', { name: 'Drawer width in grid units' });
    const decreaseWidth = sidebar.getByRole('button', {
      name: 'Decrease Drawer width in grid units',
    });

    // Given: a fresh drawer is 10 columns by 8 rows and nothing is stashed yet
    await expect(grid).toHaveAttribute(
      'aria-label',
      `Gridfinity drawer grid, ${DEFAULT_COLUMNS} columns by ${DEFAULT_ROWS} rows`
    );
    await expect(widthInput).toHaveValue(String(DEFAULT_COLUMNS));
    await expect(page.locator('[data-staging-bin-id]')).toHaveCount(0);

    // Given: one 1x1 bin in the last column (lost when the drawer narrows) and one in the
    // first column (the anchored edge, so it must survive the same resize).
    const bounds = await getGridBounds(page);
    const cellWidth = bounds.width / DEFAULT_COLUMNS;
    const cellHeight = bounds.height / DEFAULT_ROWS;
    const lastColumnX = (DEFAULT_COLUMNS - 1) * cellWidth;

    const edgeBin = await drawBinOnGrid(
      page,
      lastColumnX + cellWidth * 0.25,
      cellHeight * 0.25,
      lastColumnX + cellWidth * 0.75,
      cellHeight * 0.75
    );
    const keptBin = await drawBinOnGrid(
      page,
      cellWidth * 0.25,
      cellHeight * 0.25,
      cellWidth * 0.75,
      cellHeight * 0.75
    );

    // The app places bins with `grid-area: <row> / <column> / span h / span w`, so this
    // confirms the two bins really landed on opposite edges before the drawer is resized.
    await expect(edgeBin).toHaveAttribute('style', /grid-area: 1 \/ 10 \//);
    await expect(keptBin).toHaveAttribute('style', /grid-area: 1 \/ 1 \//);

    const edgeBinId = await edgeBin.getAttribute('data-bin-id');
    const keptBinId = await keptBin.getAttribute('data-bin-id');

    // When: the user reduces the drawer width by one grid unit
    await decreaseWidth.click();

    // Then: the baseplate grid is recomputed to the new drawer dimensions
    await expect(grid).toHaveAttribute(
      'aria-label',
      `Gridfinity drawer grid, ${DEFAULT_COLUMNS - 1} columns by ${DEFAULT_ROWS} rows`
    );
    await expect(widthInput).toHaveValue(String(DEFAULT_COLUMNS - 1));

    // Then: the bin that no longer fits is reported in the Stash - same bin id, so it was
    // moved rather than deleted - and it is gone from the grid rather than silently kept.
    // The app emits no toast and no ARIA live region for this event, so the report is
    // asserted on the Stash contents themselves.
    await expect(page.locator(`[data-staging-bin-id="${edgeBinId}"]`)).toBeVisible();
    await expect(page.locator(`[data-bin-id="${edgeBinId}"]`)).toHaveCount(0);
    await expect(stash.getByRole('button', { name: 'Stash 1 bins' })).toBeVisible();

    // Then: the bin that still fits is untouched on the recomputed grid
    await expect(page.locator(`[data-bin-id="${keptBinId}"]`)).toBeVisible();
    await expect(page.locator('[data-bin-id]')).toHaveCount(1);
  });
});

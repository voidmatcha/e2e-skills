import {
  test,
  expect,
  waitForAppReady,
  getGridBounds,
  drawBinOnGrid,
  getSidebar,
  clearAllStorage,
  resetViewport,
  getActiveDialog,
} from './fixtures';

// The default drawer the app opens with. Asserted as a precondition below so a
// leaked layout from another test fails loudly instead of skewing the drag math.
const INITIAL_COLUMNS = 10;
const INITIAL_ROWS = 8;

test.describe('Drawer resize displacement', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);
  });

  test.afterEach(async ({ page }) => {
    await clearAllStorage(page);
    await resetViewport(page);

    // Close any lingering dialogs
    const dialogs = getActiveDialog(page);
    if ((await dialogs.count()) > 0) {
      await page.keyboard.press('Escape');
      await dialogs.waitFor({ state: 'detached', timeout: 1000 }).catch(() => {});
    }
  });

  test('shrinking drawer width recomputes the baseplate grid and stashes the bin that no longer fits', async ({
    page,
  }) => {
    const sidebar = getSidebar(page);
    const gridBins = page.locator('[data-bin-id]');
    const stashedBins = page.locator('[data-staging-bin-id]');
    const widthInput = sidebar.getByRole('spinbutton', { name: 'Drawer width in grid units' });
    const decreaseWidthButton = sidebar.getByRole('button', {
      name: 'Decrease Drawer width in grid units',
    });

    // Given: a fresh 10x8 drawer with nothing on the grid and nothing stashed
    await expect(
      page.getByRole('application', {
        name: `Gridfinity drawer grid, ${INITIAL_COLUMNS} columns by ${INITIAL_ROWS} rows`,
        exact: true,
      })
    ).toBeVisible();
    await expect(widthInput).toHaveValue(String(INITIAL_COLUMNS));
    await expect(gridBins).toHaveCount(0);
    await expect(stashedBins).toHaveCount(0);

    // Given: two 2x2 bins — one at columns 1-2 that survives a one-unit shrink,
    // one at columns 9-10 whose footprint leaves the drawer at width 9.
    const bounds = await getGridBounds(page);
    const col = bounds.width / INITIAL_COLUMNS;
    const row = bounds.height / INITIAL_ROWS;

    const keptBin = await drawBinOnGrid(page, col * 0.5, row * 0.5, col * 1.5, row * 1.5);
    const keptBinId = await keptBin.getAttribute('data-bin-id');
    expect(keptBinId).not.toBeNull();

    const edgeBin = await drawBinOnGrid(page, col * 8.5, row * 0.5, col * 9.5, row * 1.5);
    const edgeBinId = await edgeBin.getAttribute('data-bin-id');
    expect(edgeBinId).not.toBeNull();
    expect(edgeBinId).not.toBe(keptBinId);

    await expect(gridBins).toHaveCount(2);
    await expect(stashedBins).toHaveCount(0);

    // When: the drawer width is reduced by one grid unit
    await decreaseWidthButton.click();

    // Then: the baseplate grid is recomputed to the new drawer dimensions
    await expect(
      page.getByRole('application', {
        name: `Gridfinity drawer grid, ${INITIAL_COLUMNS - 1} columns by ${INITIAL_ROWS} rows`,
        exact: true,
      })
    ).toBeVisible();
    await expect(widthInput).toHaveValue(String(INITIAL_COLUMNS - 1));

    // Then: the bin that no longer fits is reported in the stash — same bin id,
    // so it is surfaced to the user rather than silently kept or dropped.
    await expect(page.locator(`[data-staging-bin-id="${edgeBinId}"]`)).toBeVisible();
    await expect(stashedBins).toHaveCount(1);
    await expect(page.locator(`[data-bin-id="${edgeBinId}"]`)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Stash 1 bins', exact: true })).toBeVisible();

    // Then: the bin that still fits stays on the recomputed grid
    await expect(page.locator(`[data-bin-id="${keptBinId}"]`)).toBeVisible();
    await expect(gridBins).toHaveCount(1);
  });
});

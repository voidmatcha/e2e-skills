import {
  test,
  expect,
  waitForAppReady,
  getGridBounds,
  drawBinOnGrid,
  waitForBinSelected,
  clearAllStorage,
  resetViewport,
  getActiveDialog,
} from './fixtures';

// A brand new layout always starts on the default drawer. The grid publishes its
// own dimensions in its accessible name, so the test asserts that name before
// using these constants to turn pixels into baseplate cells.
const GRID_COLUMNS = 10;
const GRID_ROWS = 8;

// Any bin on the grid, regardless of size, as exposed to assistive tech.
const ANY_BIN = /^Bin \d+ by \d+, category /;
// The one bin this test draws: two cells across, two cells deep.
const DRAWN_BIN = /^Bin 2 by 2, category /;

test.describe('Add Bin To New Layout', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await clearAllStorage(page);
    await page.reload();
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

  test('adding a bin places it on the baseplate grid and updates the layout summary', async ({
    page,
  }) => {
    const grid = page.getByRole('application', {
      name: `Gridfinity drawer grid, ${GRID_COLUMNS} columns by ${GRID_ROWS} rows`,
    });
    const binsOnGrid = grid.getByRole('button', { name: ANY_BIN });
    const drawnBin = grid.getByRole('button', { name: DRAWN_BIN });
    const layerSummary = page.getByRole('region', { name: 'Layers' }).getByText(/% filled/);
    // The Bin List accordion appends a count badge once bins exist ("Bin List" ->
    // "Bin List 1"), so the region is matched on the substring, never exactly.
    const binList = page.getByRole('region', { name: 'Bin List' });

    // Given: a freshly auto-created, empty layout on the default 10x8 baseplate
    await expect(page).toHaveURL(/\/l\/[^/]+\/untitled-layout$/);
    await expect(grid).toBeVisible();
    await expect(binsOnGrid).toHaveCount(0);
    await expect(layerSummary).toHaveText('0% filled · 0 bins');
    await expect(binList.getByText('No bins to print')).toBeVisible();

    // When: the user drags from the centre of the first baseplate cell to the
    // centre of the diagonally adjacent one. The offsets come from the grid's
    // live bounding box rather than fixed pixels, so the gesture covers exactly
    // 2x2 cells at any zoom level or viewport.
    const gridBounds = await getGridBounds(page);
    const cellWidth = gridBounds.width / GRID_COLUMNS;
    const cellHeight = gridBounds.height / GRID_ROWS;
    await drawBinOnGrid(
      page,
      cellWidth * 0.5,
      cellHeight * 0.5,
      cellWidth * 1.5,
      cellHeight * 1.5
    );

    // Then: exactly one bin exists, and it lives inside the baseplate grid
    await expect(binsOnGrid).toHaveCount(1);

    // Then: the layout summary reflects the added bin (primary outcome)
    await expect(layerSummary).toHaveText('5% filled · 1 bins');

    // Then: the bin that was drawn is the 2x2 one the gesture described
    await expect(drawnBin).toBeVisible();

    // Then: the print list — a second, independent summary surface — agrees
    await expect(page.getByRole('button', { name: 'Bin List 1', exact: true })).toBeVisible();
    await expect(binList.getByRole('row', { name: /2×2/ })).toBeVisible();

    // Then: the bin is snapped onto the baseplate, not merely rendered near it.
    // A newly drawn bin animates in (animate-settle-in), so poll until the
    // measured geometry settles; rounding to whole cells is what makes this an
    // assertion about grid placement rather than about pixels.
    await waitForBinSelected(drawnBin);
    await expect
      .poll(async () => {
        const gridBox = await grid.boundingBox();
        const binBox = await drawnBin.boundingBox();
        if (!gridBox || !binBox) return null;
        return {
          column: Math.round((binBox.x - gridBox.x) / (gridBox.width / GRID_COLUMNS)),
          row: Math.round((binBox.y - gridBox.y) / (gridBox.height / GRID_ROWS)),
          columnSpan: Math.round(binBox.width / (gridBox.width / GRID_COLUMNS)),
          rowSpan: Math.round(binBox.height / (gridBox.height / GRID_ROWS)),
        };
      })
      .toEqual({ column: 0, row: 0, columnSpan: 2, rowSpan: 2 });
  });
});

import {
  test,
  expect,
  waitForAppReady,
  waitForBinCount,
  drawBinOnGrid,
  getGridBounds,
  getSidebar,
  getInspector,
  clearAllStorage,
} from './fixtures';
import type { Locator } from '@playwright/test';

// Default drawer for a brand-new layout, taken from the grid's own accessible
// name ("Gridfinity drawer grid, 10 columns by 8 rows").
const COLUMNS = 10;
const ROWS = 8;

/** Bounding box of a locator, failing loudly instead of returning null. */
async function boundsOf(locator: Locator, name: string) {
  const box = await locator.boundingBox();
  if (!box) throw new Error(`${name} has no bounding box`);
  return box;
}

test.describe('Add a bin to a new layout', () => {
  test.beforeEach(async ({ page }) => {
    // Each test gets a fresh Playwright context, so client-side storage
    // (localStorage + the IndexedDB layout library) starts empty and the app
    // bootstraps a brand-new, untitled layout.
    await page.goto('/');
    await waitForAppReady(page);
  });

  test.afterEach(async ({ page }) => {
    await clearAllStorage(page);
  });

  test('drawing on an empty baseplate places the bin on the grid and updates the layout summary', async ({
    page,
  }) => {
    const baseplateGrid = page.getByRole('application', {
      name: `Gridfinity drawer grid, ${COLUMNS} columns by ${ROWS} rows`,
    });
    const layoutSummary = getSidebar(page).getByText(/% filled/);
    const inspector = getInspector(page);
    const placedBin = baseplateGrid.getByRole('button', { name: 'Bin 2 by 2, category Coral' });

    // Given: a new layout whose baseplate is empty
    await expect(baseplateGrid).toBeVisible();
    await expect(layoutSummary).toHaveText('0% filled · 0 bins');
    await expect(inspector.getByText('No bins to print')).toBeVisible();
    await waitForBinCount(page, 0);

    // When: the user drags across the 2x2 block of baseplate cells anchored at
    // the grid's first column and first row. Offsets are cell centres derived
    // from the live grid box, so the drawn size is 2x2 at any viewport.
    const emptyGridBox = await getGridBounds(page);
    const cellWidth = emptyGridBox.width / COLUMNS;
    const cellHeight = emptyGridBox.height / ROWS;
    await drawBinOnGrid(page, cellWidth * 0.5, cellHeight * 0.5, cellWidth * 1.5, cellHeight * 1.5);

    // Then: the bin is placed on the baseplate grid ...
    await expect(placedBin).toBeVisible();

    // ... covering exactly the two columns and two rows that were dragged over.
    // Tolerance is half a cell, so a bin one cell off or one unit too small
    // still fails.
    const gridBox = await getGridBounds(page);
    const binBox = await boundsOf(placedBin, 'placed bin');
    const tolerance = Math.min(cellWidth, cellHeight) / 2;
    expect(Math.abs(binBox.x - gridBox.x)).toBeLessThan(tolerance);
    expect(Math.abs(binBox.y - gridBox.y)).toBeLessThan(tolerance);
    expect(Math.abs(binBox.width - cellWidth * 2)).toBeLessThan(tolerance);
    expect(Math.abs(binBox.height - cellHeight * 2)).toBeLessThan(tolerance);

    // ... and the layout summary reflects the added bin: 4 of 80 cells filled.
    await expect(layoutSummary).toHaveText('5% filled · 1 bins');
    await expect(inspector.getByText('No bins to print')).toHaveCount(0);
    await expect(inspector.getByRole('row').filter({ hasText: '2×2' })).toHaveCount(1);
    await expect(inspector.getByText(/^\d+ bins$/)).toHaveText('1 bins');
  });
});

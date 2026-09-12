import {
  test,
  expect,
  waitForAppReady,
  getGridBounds,
  getSidebar,
  clearAllStorage,
  resetViewport,
  closeDialogs,
} from './fixtures';

/**
 * The baseplate advertises its own dimensions in its accessible name, and the cells are
 * laid out on a uniform pitch, so cell centres can be derived from the grid box instead of
 * hard-coding pixels that would break whenever auto-zoom changes.
 */
const GRID_NAME = 'Gridfinity drawer grid, 10 columns by 8 rows';
const GRID_COLUMNS = 10;
const GRID_ROWS = 8;

/** Drawing across two columns and two rows fills 4 of the 80 cells = 5% of the layer. */
const EXPECTED_SUMMARY = '5% filled · 1 bins';

type Box = { x: number; y: number; width: number; height: number };
type Point = { x: number; y: number };

const covers = (box: Box, point: Point): boolean =>
  point.x >= box.x &&
  point.x <= box.x + box.width &&
  point.y >= box.y &&
  point.y <= box.y + box.height;

const isWithin = (outer: Box, inner: Box): boolean =>
  inner.x >= outer.x &&
  inner.y >= outer.y &&
  inner.x + inner.width <= outer.x + outer.width &&
  inner.y + inner.height <= outer.y + outer.height;

const cellCentre = (bounds: Box, column: number, row: number): Point => ({
  x: bounds.x + (column + 0.5) * (bounds.width / GRID_COLUMNS),
  y: bounds.y + (row + 0.5) * (bounds.height / GRID_ROWS),
});

test.describe('Add bin to a new layout', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);
  });

  test.afterEach(async ({ page }) => {
    await clearAllStorage(page);
    await resetViewport(page);
    await closeDialogs(page);
  });

  test('places the drawn bin on the baseplate grid and updates the layout summary', async ({
    page,
  }) => {
    const grid = page.getByRole('application', { name: GRID_NAME });
    const layoutSummary = getSidebar(page).getByText(/% filled/);
    // The Bin List section header gains a count badge once bins exist, so its accessible name
    // grows from "Bin List" to "Bin List 1" — match the stable prefix rather than the whole name.
    const binList = page.getByRole('region', { name: /^Bin List/ });

    // A fresh context starts with empty client-side storage, so the auto-created layout is
    // empty. Both checks are independent of the layer-summary string the test asserts later.
    await expect(grid.locator('[data-bin-id]')).toHaveCount(0);
    await expect(binList).toContainText('No bins to print');

    // Drag across the cell at column 3 / row 4 into the cell at column 4 / row 5.
    const bounds = await getGridBounds(page);
    const dragFrom = cellCentre(bounds, 2, 3);
    const dragTo = cellCentre(bounds, 3, 4);

    await page.mouse.move(dragFrom.x, dragFrom.y);
    await page.mouse.down();
    await page.mouse.move(dragTo.x, dragTo.y, { steps: 5 });
    await page.mouse.up();

    // The accessible name carries the footprint and the category, so a bin drawn with the
    // wrong dimensions cannot satisfy this locator.
    const bin = grid.getByRole('button', { name: 'Bin 2 by 2, category Coral' });
    await expect(bin).toBeVisible();
    await expect(grid.locator('[data-bin-id]')).toHaveCount(1);

    // Placement: the bin renders inside the baseplate and spans the two cells that were
    // dragged across, rather than merely existing somewhere in the document.
    await expect
      .poll(async () => {
        const binBox = await bin.boundingBox();
        const gridBox = await grid.boundingBox();
        if (!binBox || !gridBox) return null;
        return {
          insideBaseplate: isWithin(gridBox, binBox),
          coversFirstCell: covers(binBox, dragFrom),
          coversSecondCell: covers(binBox, dragTo),
        };
      })
      .toEqual({ insideBaseplate: true, coversFirstCell: true, coversSecondCell: true });

    // Primary outcome: the layout summary reports both the new bin and the coverage it adds.
    await expect(layoutSummary).toHaveText(EXPECTED_SUMMARY);

    // The print list is a separate derived aggregation, so it is asserted on its own.
    const binListRow = binList.getByRole('row', { name: /2×2/ });
    const binListCells = binListRow.getByRole('cell');
    // The Size / H / Qty / Fil. cells carry no accessible name, so they are addressed by column.
    // JUSTIFIED: Size is the first column of that table.
    await expect(binListCells.first()).toHaveText('2×2');
    // JUSTIFIED: Qty is the third column of that table.
    await expect(binListCells.nth(2)).toHaveText('1');
  });
});

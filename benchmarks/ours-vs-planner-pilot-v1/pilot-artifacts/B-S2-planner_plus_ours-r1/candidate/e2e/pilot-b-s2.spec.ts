import {
  test,
  expect,
  waitForAppReady,
  getGridBounds,
  getSidebar,
  waitForBinCount,
  clearAllStorage,
  resetViewport,
} from './fixtures';

/**
 * Scenario B-S2 — resizing the drawer recomputes the baseplate grid and reports
 * the bin that no longer fits.
 *
 * The drawer starts at 10 columns x 8 rows. A 2x2 bin drawn in the two
 * right-most columns (9-10) stops fitting once the width is shrunk to 5.
 * A width shrink trims the highest-index columns and leaves surviving bins
 * un-renumbered, so the right-most columns are the deterministic probe.
 *
 * The app has no toast or live-region announcement for this displacement: the
 * report surface is the Stash panel (its "Stash N bins" trigger plus the staged
 * bin node), so that is what this spec asserts.
 */

const INITIAL_COLUMNS = 10;
const INITIAL_ROWS = 8;
const SHRUNK_COLUMNS = 5;

const gridName = (columns: number, rows: number) =>
  `Gridfinity drawer grid, ${columns} columns by ${rows} rows`;

test.describe('Drawer resize displacement', () => {
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

  test('shrinking drawer width recomputes the grid and stashes the bin that no longer fits', async ({
    page,
  }) => {
    // Scoped to the desktop shell (>= BREAKPOINTS.LG, 900px): below 768px the
    // default drawer is 6x9 rather than 10x8, and on tablet widths the sidebar
    // holding the drawer-size steppers sits in a panel overlay that starts closed.
    const viewport = page.viewportSize();
    test.skip((viewport?.width ?? 0) < 900, 'desktop-only drawer size controls');

    // Given: a fresh 10x8 drawer
    // (exact: true — the default substring match would also accept a wider grid,
    // e.g. "15 columns by 8 rows" contains "5 columns by 8 rows")
    await expect(
      page.getByRole('application', {
        name: gridName(INITIAL_COLUMNS, INITIAL_ROWS),
        exact: true,
      })
    ).toBeVisible();

    const widthInput = getSidebar(page).getByRole('spinbutton', {
      name: 'Drawer width in grid units',
    });
    await expect(widthInput).toHaveValue(String(INITIAL_COLUMNS));

    // Given: a 2x2 bin occupying the two right-most columns of the drawer
    const bounds = await getGridBounds(page);
    const cellWidth = bounds.width / INITIAL_COLUMNS;
    const cellHeight = bounds.height / INITIAL_ROWS;
    await page.mouse.move(bounds.x + cellWidth * 8.5, bounds.y + cellHeight * 0.5);
    await page.mouse.down();
    await page.mouse.move(bounds.x + cellWidth * 9.5, bounds.y + cellHeight * 1.5, { steps: 5 });
    await page.mouse.up();
    await waitForBinCount(page, 1);

    const binId = (await page.locator('[data-bin-id]').getAttribute('data-bin-id')) ?? '';
    expect(binId).not.toBe('');

    // The probe must genuinely sit beyond the post-shrink boundary, otherwise
    // "no longer fits" is assumed rather than established — a regression that
    // stashed every bin on any resize would pass the assertions below.
    const binBox = await page.locator('[data-bin-id]').boundingBox();
    expect(binBox?.x ?? 0).toBeGreaterThan(bounds.x + cellWidth * SHRUNK_COLUMNS);

    // When: the drawer width is shrunk so that bin no longer fits
    // (the stepper input commits on blur, not on fill)
    await widthInput.fill(String(SHRUNK_COLUMNS));
    await widthInput.blur();

    // Then: the baseplate grid is recomputed on the width axis only
    await expect(
      page.getByRole('application', {
        name: gridName(SHRUNK_COLUMNS, INITIAL_ROWS),
        exact: true,
      })
    ).toBeVisible();

    // Then: the bin is not silently kept on the grid ...
    await expect(page.locator('[data-bin-id]')).toHaveCount(0);

    // ... it is reported in the stash ...
    await expect(page.getByRole('button', { name: 'Stash 1 bins' })).toBeVisible();

    // ... and it is the same bin, not a replacement
    await expect(page.locator(`[data-staging-bin-id="${binId}"]`)).toBeVisible();
  });
});

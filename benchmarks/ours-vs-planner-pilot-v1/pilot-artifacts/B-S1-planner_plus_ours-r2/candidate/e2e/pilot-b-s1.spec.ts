import {
  test,
  expect,
  waitForAppReady,
  getGridBounds,
  clearAllStorage,
  resetViewport,
  closeDialogs,
} from './fixtures';

/**
 * The default drawer for a new layout, taken from the grid's own accessible name
 * ("Gridfinity drawer grid, 10 columns by 8 rows"). Cell size is a function of the
 * auto-fit zoom, so drag coordinates are derived from the live grid bounds at run
 * time instead of from literal pixel offsets.
 */
const GRID_COLUMNS = 10;
const GRID_ROWS = 8;
const GRID_NAME = 'Gridfinity drawer grid, 10 columns by 8 rows';

test.describe('Add a bin to a new layout', () => {
  // The layout summary is rendered through the `layers.stats` i18n key and the app
  // picks its locale from navigator.languages (src/i18n/detection.ts), so the
  // English summary text is only deterministic with the locale pinned.
  test.use({ locale: 'en-US' });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);
  });

  test.afterEach(async ({ page }) => {
    await clearAllStorage(page);
    await resetViewport(page);
    await closeDialogs(page);
  });

  test('placing a bin on the baseplate grid updates the layout summary', async ({ page }) => {
    const grid = page.getByRole('application', { name: GRID_NAME, exact: true });
    const layoutSummary = page
      .getByRole('region', { name: 'Layers', exact: true })
      .getByText(/^\d+% filled · \d+ bins$/);
    const placedBin = grid.getByRole('button', { name: 'Bin 3 by 3, category Coral' });

    // Given: a new layout whose baseplate grid is empty
    await expect(grid).toBeVisible();
    await expect(page.locator('[data-bin-id]')).toHaveCount(0);
    await expect(layoutSummary).toHaveText('0% filled · 0 bins');

    // When: the user drags across a 3x3 block of cells, from the first column of the
    // top row to the third column of the third row
    const bounds = await getGridBounds(page);
    const cellWidth = bounds.width / GRID_COLUMNS;
    const cellHeight = bounds.height / GRID_ROWS;
    await page.mouse.move(bounds.x + cellWidth * 0.5, bounds.y + cellHeight * 0.5);
    await page.mouse.down();
    await page.mouse.move(bounds.x + cellWidth * 2.5, bounds.y + cellHeight * 2.5, { steps: 5 });
    await page.mouse.up();

    // Then: a 3x3 bin is rendered inside the baseplate grid
    await expect(placedBin).toBeVisible();

    // Then: the layout summary counts the new bin and the 9 of 80 grid cells it covers.
    // Coverage is Math.round(cells / drawerCells * 100) (LayerPanel.tsx), so the exact
    // 11% also pins the bin's footprint: 3x2 would report 8% and 4x3 would report 15%.
    await expect(layoutSummary).toHaveText('11% filled · 1 bins');

    // And: the bin really occupies the dragged column of the baseplate, not merely some
    // spot on it — deselecting and then selecting column 1 picks this bin back up.
    await page.keyboard.press('Escape');
    await expect(placedBin).toHaveAttribute('aria-pressed', 'false');
    await page.getByRole('button', { name: 'Select bins in column 1', exact: true }).click();
    await expect(placedBin).toHaveAttribute('aria-pressed', 'true');
  });
});

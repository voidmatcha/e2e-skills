import {
  test,
  expect,
  waitForAppReady,
  getSidebar,
  getInspector,
  clearAllStorage,
  resetViewport,
} from './fixtures';

// The layout summary and bin list this spec asserts on live in the desktop
// shell: below BREAKPOINTS.LG (900) App renders the tablet overlay or the
// mobile shell, and the mobile tree has no [data-sidebar] / [data-inspector]
// at all. Without this guard the spec is guaranteed red on the mobile-chrome,
// mobile-safari and tablet projects rather than meaningfully skipped.
test.describe('Add Bin To New Layout', () => {
  test.skip(
    ({ viewport }) => !viewport || viewport.width < 900,
    'Layout summary and bin list are desktop-shell only (width >= 900)'
  );

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

  test('adding a bin places it on the baseplate grid and the layout summary reflects it', async ({
    page,
  }) => {
    const grid = page.getByRole('application', { name: /Gridfinity drawer grid/i });
    // Bins render as buttons inside the grid region, so scoping to `grid` is what
    // proves a bin is on the baseplate rather than merely somewhere on the page.
    const binsOnGrid = grid.getByRole('button', { name: /^Bin \d+ by \d+/ });
    const layerSummary = getSidebar(page).getByText(/filled · \d+ bins/);
    const binListEmptyState = getInspector(page).getByText('No bins to print');
    const binListRow = getInspector(page)
      .getByRole('region', { name: /^Bin List/ })
      .getByRole('row')
      .filter({ hasText: '1×1' });

    // Given: a new layout on the default empty baseplate. Asserting the grid's
    // accessible name pins the 10×8 geometry the click arithmetic below relies on.
    await expect(grid).toHaveAttribute('aria-label', 'Gridfinity drawer grid, 10 columns by 8 rows');
    await expect(binsOnGrid).toHaveCount(0);
    await expect(layerSummary).toHaveText('0% filled · 0 bins');
    await expect(binListEmptyState).toBeVisible();

    // When: the user clicks the centre of one empty cell. Column 3 / row 5 is
    // deliberately asymmetric so that transposing the grid axes cannot satisfy
    // the placement assertions below. Cell centres are derived from the grid box
    // because individual cells are not exposed as elements; the half-unit
    // offsets keep the click clear of cell borders.
    const gridBox = await grid.boundingBox();
    if (!gridBox) throw new Error('Grid bounding box unavailable');
    await page.mouse.click(
      gridBox.x + (gridBox.width * 2.5) / 10,
      gridBox.y + (gridBox.height * 4.5) / 8
    );

    // Then: exactly one bin is placed on the baseplate grid...
    await expect(binsOnGrid).toHaveCount(1);
    await expect(binsOnGrid).toBeVisible();

    // ...and the layout summary reflects the added bin.
    await expect(layerSummary).toBeVisible();
    await expect(layerSummary).toHaveText('1% filled · 1 bins');

    // The bin occupies the single cell that was clicked. Bin.tsx sets gridColumn
    // and gridRow inline, so the resolved grid placement is the app's own
    // statement of *where* on the baseplate the bin landed — a visibility check
    // alone cannot tell one cell from another.
    await expect(binsOnGrid).toHaveAttribute('aria-label', 'Bin 1 by 1, category Coral');
    await expect(binsOnGrid).toHaveCSS('grid-column-start', '3');
    await expect(binsOnGrid).toHaveCSS('grid-row-start', '5');
    await expect(binsOnGrid).toHaveCSS('grid-column-end', 'span 1');
    await expect(binsOnGrid).toHaveCSS('grid-row-end', 'span 1');

    // The inspector's bin list leaves its empty state and reports the bin's own
    // row data (size, height, quantity), not merely that a row mentioning 1×1
    // exists — the quantity cell is what a broken roll-up would get wrong.
    await expect(binListEmptyState).toBeHidden();
    await expect(binListRow.getByRole('cell')).toHaveText(['1×1', '3u', '1', /^\d+\.\d+$/]);
  });
});

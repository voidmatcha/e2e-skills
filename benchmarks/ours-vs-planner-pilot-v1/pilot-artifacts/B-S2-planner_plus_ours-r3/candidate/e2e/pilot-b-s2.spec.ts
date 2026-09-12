import {
  test,
  expect,
  waitForAppReady,
  getSidebar,
  getStash,
  clearAllStorage,
  resetViewport,
} from './fixtures';

/**
 * Shrinking the drawer must do two things at once: recompute the baseplate grid
 * to the new width, and surface every bin whose footprint no longer fits in the
 * stash instead of quietly leaving it on (or past) the new boundary.
 *
 * The stash is the app's only displacement report — there is no toast, and the
 * Bin List / category badge do not distinguish a displaced bin from a deleted
 * one. Asserting bin identity (the pre-resize `data-bin-id` reappearing verbatim
 * as `data-staging-bin-id`) is therefore what separates "moved to the stash"
 * from "destroyed and replaced".
 */
test.describe('Drawer resize displacement', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);
  });

  test.afterEach(async ({ page }) => {
    await clearAllStorage(page);
    await resetViewport(page);
  });

  test('shrinking drawer width recomputes the grid and stashes the bin that no longer fits', async ({
    page,
  }) => {
    const sidebar = getSidebar(page);
    const grid = page.getByRole('application');
    const widthInput = sidebar.getByRole('spinbutton', { name: 'Drawer width in grid units' });
    const gridBins = page.locator('[data-bin-id]');
    const stashedBins = page.locator('[data-staging-bin-id]');
    const columnHeaders = page.getByRole('button', { name: /^Select bins in column \d+$/ });

    // Given: a default 10x8 drawer with nothing stashed yet
    await expect(grid).toHaveAttribute(
      'aria-label',
      'Gridfinity drawer grid, 10 columns by 8 rows'
    );
    await expect(widthInput).toHaveValue('10');
    await expect(stashedBins).toHaveCount(0);

    // Given: the layer is filled, which lays down four bins including a 4-wide
    // one that ends exactly on column 10
    await sidebar.getByRole('button', { name: 'Fill 80 gaps' }).click();
    await expect(gridBins).toHaveCount(4);

    const doomedBin = page.locator('[data-bin-id][aria-label="Bin 4 by 6, category Coral"]');
    await expect(doomedBin).toBeVisible();
    const doomedBinId = await doomedBin.getAttribute('data-bin-id');
    expect(doomedBinId).toBeTruthy();

    // When: the user shrinks the drawer from 10 to 8 grid units wide
    await widthInput.fill('8');
    await widthInput.blur();

    // Then: the baseplate grid is recomputed to the new width
    await expect(grid).toHaveAttribute('aria-label', 'Gridfinity drawer grid, 8 columns by 8 rows');
    await expect(columnHeaders).toHaveCount(8);

    // Then: the bin that no longer fits is reported in the stash, under the very
    // same id it had on the grid (a move, not a delete-and-recreate)
    await expect(page.locator(`[data-staging-bin-id="${doomedBinId}"]`)).toBeVisible();

    // Then: it is not silently kept on the grid as well
    await expect(page.locator(`[data-bin-id="${doomedBinId}"]`)).toHaveCount(0);
    await expect(gridBins).toHaveCount(2);

    // Then: the stash header tells the user how many bins were displaced
    await expect(stashedBins).toHaveCount(2);
    await expect(getStash(page).getByRole('button', { name: 'Stash 2 bins' })).toBeVisible();

    // Then: nothing left on the grid overhangs the new 8-column boundary.
    // Bin footprints are only exposed through CSS grid placement, so read them
    // after the assertions above have settled the post-resize state.
    for (const bin of await gridBins.all()) {
      // JUSTIFIED: the serialized `style` attribute collapses the placement
      // longhands into a different shorthand per engine (grid-area in Blink,
      // grid-column/grid-row in Gecko/WebKit); the computed longhands are the
      // only cross-engine stable read, and no Playwright API exposes them.
      const placement = await bin.evaluate((element) => {
        const computed = getComputedStyle(element);
        return { start: computed.gridColumnStart, end: computed.gridColumnEnd };
      });

      const columnStart = Number.parseInt(placement.start, 10);
      const span = /^span\s+(\d+)$/.exec(placement.end.trim());
      const columnEnd = span
        ? columnStart + Number(span[1])
        : Number.parseInt(placement.end, 10);

      expect(columnStart, `unexpected grid-column-start: ${placement.start}`).not.toBeNaN();
      expect(columnEnd, `unexpected grid-column-end: ${placement.end}`).not.toBeNaN();
      expect(columnEnd - 1).toBeLessThanOrEqual(8);
    }
  });
});

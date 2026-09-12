import type { Locator, Page } from '@playwright/test';
import {
  test,
  expect,
  waitForAppReady,
  getGridBounds,
  getSidebar,
  getActiveDialog,
  clearAllStorage,
  resetViewport,
} from './fixtures';

// Default drawer of a new layout, published by the grid's accessible name.
const GRID_COLUMNS = 10;
const GRID_ROWS = 8;

/**
 * The layout record the app persists in IndexedDB (`gridfinity-db` -> `layouts`).
 * Records are stored as an opaque compressed string, so the raw record is only
 * ever compared against an earlier snapshot of itself - it proves the auto-save
 * actually rewrote the layout at the persistence boundary rather than the grid
 * merely re-rendering from memory.
 */
async function readPersistedLayout(page: Page): Promise<string> {
  // JUSTIFIED: evaluate() with raw IndexedDB - Playwright has no API for reading IndexedDB.
  return page.evaluate(async () => {
    const databases = await indexedDB.databases();
    if (!databases.some((database) => database.name === 'gridfinity-db')) return '';

    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('gridfinity-db');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });

    try {
      if (!db.objectStoreNames.contains('layouts')) return '';
      const records = await new Promise<unknown[]>((resolve, reject) => {
        const request = db.transaction('layouts', 'readonly').objectStore('layouts').getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      return records.map((record) => String(record)).join('|');
    } finally {
      db.close();
    }
  });
}

async function boundingBoxOf(locator: Locator, label: string) {
  const box = await locator.boundingBox();
  if (!box) throw new Error(`${label} has no bounding box`);
  return box;
}

test.describe('Add a bin to a new layout', () => {
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

  test('adding a bin places it on the baseplate grid and updates the layout summary', async ({
    page,
  }) => {
    // Given: a new layout whose baseplate grid is empty
    const grid = page.getByRole('application');
    const placedBins = page.locator('[data-bin-id]');
    const layoutSummary = getSidebar(page).getByText(/% filled/);

    await expect(grid).toHaveAccessibleName(
      `Gridfinity drawer grid, ${GRID_COLUMNS} columns by ${GRID_ROWS} rows`
    );
    await expect(placedBins).toHaveCount(0);
    await expect(layoutSummary).toHaveText('0% filled · 0 bins');
    const emptyLayoutRecord = await readPersistedLayout(page);

    // When: the user clicks the first cell of the baseplate grid
    const gridBounds = await getGridBounds(page);
    const cellWidth = gridBounds.width / GRID_COLUMNS;
    const cellHeight = gridBounds.height / GRID_ROWS;
    const clickX = gridBounds.x + cellWidth / 2;
    const clickY = gridBounds.y + cellHeight / 2;
    await page.mouse.click(clickX, clickY);

    // Then: a 1x1 bin is rendered on the baseplate grid
    const placedBin = grid.getByRole('button', { name: /^Bin 1 by 1/ });
    await expect(placedBin).toBeVisible();
    await expect(placedBins).toHaveCount(1);

    // Then: the bin occupies the single grid cell the user clicked
    const binBox = await boundingBoxOf(placedBin, 'placed bin');
    expect(binBox.width).toBeLessThanOrEqual(cellWidth + 1);
    expect(binBox.height).toBeLessThanOrEqual(cellHeight + 1);
    expect(binBox.x).toBeLessThanOrEqual(clickX);
    expect(clickX).toBeLessThanOrEqual(binBox.x + binBox.width);
    expect(binBox.y).toBeLessThanOrEqual(clickY);
    expect(clickY).toBeLessThanOrEqual(binBox.y + binBox.height);

    // Then: the layout summary reflects the added bin (1 of 80 cells covered)
    await expect(layoutSummary).toHaveText('1% filled · 1 bins');

    // Then: the added bin is written to the persisted layout, not just to the DOM
    await expect
      .poll(() => readPersistedLayout(page), { timeout: 10000 })
      .not.toBe(emptyLayoutRecord);

    // Then: a reload - which discards every in-memory optimistic update - still
    // shows exactly the one added bin and the same layout summary
    await page.reload();
    await waitForAppReady(page);
    await expect(placedBins).toHaveCount(1);
    await expect(layoutSummary).toHaveText('1% filled · 1 bins');
  });
});

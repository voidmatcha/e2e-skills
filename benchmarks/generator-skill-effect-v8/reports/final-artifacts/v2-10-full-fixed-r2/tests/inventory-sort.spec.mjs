import { expect, test } from "@playwright/test";

const columns = ["Name", "Price", "Stock"];

const columnHeader = (page, name) => page.getByRole("columnheader", { name });
const sortButton = (page, name) => page.getByRole("button", { name });
const nameCells = (page) => page.locator("tbody td:first-child");

async function expectSortState(page, sortedColumn, direction) {
  for (const column of columns) {
    await expect(columnHeader(page, column)).toHaveAttribute(
      "aria-sort",
      column === sortedColumn ? direction : "none",
    );
  }
}

async function expectNames(page, names) {
  await expect(nameCells(page)).toHaveText(names);
}

test.describe("inventory table sorting", () => {
  test("sorts each column in ascending and descending order", async ({ page }) => {
    await page.goto("/");

    await sortButton(page, "Name").click();
    await expect(page).toHaveURL("/?sort=name&dir=asc");
    await expectSortState(page, "Name", "ascending");
    await expectNames(page, [
      "Anvil",
      "Bellows Out of stock",
      "Chisel set",
      "Drawknife",
      "Emery cloth Out of stock",
      "Froe",
    ]);

    await sortButton(page, "Name").click();
    await expect(page).toHaveURL("/?sort=name&dir=desc");
    await expectSortState(page, "Name", "descending");
    await expectNames(page, [
      "Froe",
      "Emery cloth Out of stock",
      "Drawknife",
      "Chisel set",
      "Bellows Out of stock",
      "Anvil",
    ]);

    await sortButton(page, "Price").click();
    await expect(page).toHaveURL("/?sort=price&dir=asc");
    await expectSortState(page, "Price", "ascending");
    await expectNames(page, [
      "Emery cloth Out of stock",
      "Froe",
      "Chisel set",
      "Bellows Out of stock",
      "Drawknife",
      "Anvil",
    ]);

    await sortButton(page, "Price").click();
    await expect(page).toHaveURL("/?sort=price&dir=desc");
    await expectSortState(page, "Price", "descending");
    await expectNames(page, [
      "Anvil",
      "Drawknife",
      "Bellows Out of stock",
      "Chisel set",
      "Froe",
      "Emery cloth Out of stock",
    ]);

    await sortButton(page, "Stock").click();
    await expect(page).toHaveURL("/?sort=stock&dir=asc");
    await expectSortState(page, "Stock", "ascending");
    await expectNames(page, [
      "Bellows Out of stock",
      "Emery cloth Out of stock",
      "Drawknife",
      "Anvil",
      "Froe",
      "Chisel set",
    ]);

    await sortButton(page, "Stock").click();
    await expect(page).toHaveURL("/?sort=stock&dir=desc");
    await expectSortState(page, "Stock", "descending");
    await expectNames(page, [
      "Chisel set",
      "Froe",
      "Anvil",
      "Drawknife",
      "Bellows Out of stock",
      "Emery cloth Out of stock",
    ]);
  });

  test("restores sort order and header state from the URL", async ({ page }) => {
    await page.goto("/?sort=price&dir=desc");

    await expectSortState(page, "Price", "descending");
    await expectNames(page, [
      "Anvil",
      "Drawknife",
      "Bellows Out of stock",
      "Chisel set",
      "Froe",
      "Emery cloth Out of stock",
    ]);

    await page.reload();

    await expect(page).toHaveURL("/?sort=price&dir=desc");
    await expectSortState(page, "Price", "descending");
    await expectNames(page, [
      "Anvil",
      "Drawknife",
      "Bellows Out of stock",
      "Chisel set",
      "Froe",
      "Emery cloth Out of stock",
    ]);
  });

  test("marks rows with zero stock as out of stock", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByText("Out of stock")).toHaveCount(2);
    await expect(nameCells(page)).toHaveText([
      "Anvil",
      "Bellows Out of stock",
      "Chisel set",
      "Drawknife",
      "Emery cloth Out of stock",
      "Froe",
    ]);
  });
});

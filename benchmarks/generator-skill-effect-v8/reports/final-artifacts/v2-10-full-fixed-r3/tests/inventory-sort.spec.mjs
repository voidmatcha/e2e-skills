import { expect, test } from "@playwright/test";

const inventory = [
  { name: "Anvil", price: 120, stock: 2 },
  { name: "Bellows", price: 42, stock: 0 },
  { name: "Chisel set", price: 15, stock: 14 },
  { name: "Drawknife", price: 68, stock: 1 },
  { name: "Emery cloth", price: 7, stock: 0 },
  { name: "Froe", price: 9.5, stock: 6 },
];

const columns = [
  { key: "name", label: "Name" },
  { key: "price", label: "Price" },
  { key: "stock", label: "Stock" },
];

const expectedNames = (key, dir = "asc") => {
  const sorted = [...inventory].sort((a, b) => {
    const result =
      typeof a[key] === "number"
        ? a[key] - b[key]
        : a[key].localeCompare(b[key]);
    return dir === "desc" ? -result : result;
  });

  return sorted.map(({ name }) => name);
};

const inventoryRows = (page) =>
  page.getByRole("table").locator("tbody tr");

const columnHeader = (page, label) => {
  return page.getByRole("columnheader", { name: label, exact: true });
};

const sortButton = (page, label) => {
  return columnHeader(page, label).getByRole("button", {
    name: label,
    exact: true,
  });
};

const expectRowOrder = async (page, names) => {
  await expect(inventoryRows(page)).toContainText(names);
};

const expectSortState = async (page, activeKey, direction) => {
  for (const { key, label } of columns) {
    await expect(columnHeader(page, label)).toHaveAttribute(
      "aria-sort",
      key === activeKey ? direction : "none",
    );
  }
};

test.describe("inventory table sorting", () => {
  test("sorts each column ascending and descending from the table headers", async ({
    page,
  }) => {
    await page.goto("/");

    for (const { key, label } of columns) {
      await sortButton(page, label).click();
      await expectRowOrder(page, expectedNames(key, "asc"));
      await expectSortState(page, key, "ascending");
      await expect(page).toHaveURL(`/?sort=${key}&dir=asc`);

      await sortButton(page, label).click();
      await expectRowOrder(page, expectedNames(key, "desc"));
      await expectSortState(page, key, "descending");
      await expect(page).toHaveURL(`/?sort=${key}&dir=desc`);
    }
  });

  test("loads the requested sort from the URL and keeps it after reload", async ({
    page,
  }) => {
    await page.goto("/?sort=price&dir=desc");

    await expectRowOrder(page, expectedNames("price", "desc"));
    await expectSortState(page, "price", "descending");

    await page.reload();

    await expectRowOrder(page, expectedNames("price", "desc"));
    await expectSortState(page, "price", "descending");
    await expect(page).toHaveURL("/?sort=price&dir=desc");
  });

  test("marks zero-stock rows with out-of-stock badges", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByText("Out of stock")).toHaveCount(2);
    await expect(inventoryRows(page).filter({ hasText: "Bellows" })).toContainText(
      "Out of stock",
    );
    await expect(
      inventoryRows(page).filter({ hasText: "Emery cloth" }),
    ).toContainText("Out of stock");
  });
});

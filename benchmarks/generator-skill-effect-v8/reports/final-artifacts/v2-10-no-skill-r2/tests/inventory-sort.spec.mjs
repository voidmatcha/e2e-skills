import { expect, test } from "@playwright/test";

const columns = {
  name: 0,
  price: 1,
  stock: 2,
};

async function columnValues(page, column) {
  const cells = page.locator("tbody tr").locator(`td:nth-child(${columns[column] + 1})`);
  return cells.allTextContents();
}

function header(page, name) {
  return page.getByRole("columnheader", { name });
}

test("sorts inventory columns and reflects the active sort in the URL and headers", async ({ page }) => {
  await page.goto("/");

  await expect(header(page, "Name")).toHaveAttribute("aria-sort", "none");
  await expect(header(page, "Price")).toHaveAttribute("aria-sort", "none");
  await expect(header(page, "Stock")).toHaveAttribute("aria-sort", "none");

  await page.getByRole("button", { name: "Name" }).click();
  await expect(page).toHaveURL("/?sort=name&dir=asc");
  await expect(header(page, "Name")).toHaveAttribute("aria-sort", "ascending");
  await expect(header(page, "Price")).toHaveAttribute("aria-sort", "none");
  await expect(header(page, "Stock")).toHaveAttribute("aria-sort", "none");
  await expect(await columnValues(page, "name")).toEqual([
    "Anvil",
    "Bellows Out of stock",
    "Chisel set",
    "Drawknife",
    "Emery cloth Out of stock",
    "Froe",
  ]);

  await page.getByRole("button", { name: "Name" }).click();
  await expect(page).toHaveURL("/?sort=name&dir=desc");
  await expect(header(page, "Name")).toHaveAttribute("aria-sort", "descending");
  await expect(await columnValues(page, "name")).toEqual([
    "Froe",
    "Emery cloth Out of stock",
    "Drawknife",
    "Chisel set",
    "Bellows Out of stock",
    "Anvil",
  ]);

  await page.getByRole("button", { name: "Price" }).click();
  await expect(page).toHaveURL("/?sort=price&dir=asc");
  await expect(header(page, "Name")).toHaveAttribute("aria-sort", "none");
  await expect(header(page, "Price")).toHaveAttribute("aria-sort", "ascending");
  await expect(header(page, "Stock")).toHaveAttribute("aria-sort", "none");
  await expect(await columnValues(page, "price")).toEqual([
    "$7.00",
    "$9.50",
    "$15.00",
    "$42.00",
    "$68.00",
    "$120.00",
  ]);

  await page.getByRole("button", { name: "Price" }).click();
  await expect(page).toHaveURL("/?sort=price&dir=desc");
  await expect(header(page, "Price")).toHaveAttribute("aria-sort", "descending");
  await expect(await columnValues(page, "price")).toEqual([
    "$120.00",
    "$68.00",
    "$42.00",
    "$15.00",
    "$9.50",
    "$7.00",
  ]);

  await page.getByRole("button", { name: "Stock" }).click();
  await expect(page).toHaveURL("/?sort=stock&dir=asc");
  await expect(header(page, "Name")).toHaveAttribute("aria-sort", "none");
  await expect(header(page, "Price")).toHaveAttribute("aria-sort", "none");
  await expect(header(page, "Stock")).toHaveAttribute("aria-sort", "ascending");
  await expect(await columnValues(page, "stock")).toEqual(["0", "0", "1", "2", "6", "14"]);

  await page.getByRole("button", { name: "Stock" }).click();
  await expect(page).toHaveURL("/?sort=stock&dir=desc");
  await expect(header(page, "Stock")).toHaveAttribute("aria-sort", "descending");
  await expect(await columnValues(page, "stock")).toEqual(["14", "6", "2", "1", "0", "0"]);
});

test("opens a sorted URL directly and preserves sort after reload", async ({ page }) => {
  await page.goto("/?sort=price&dir=desc");

  await expect(header(page, "Name")).toHaveAttribute("aria-sort", "none");
  await expect(header(page, "Price")).toHaveAttribute("aria-sort", "descending");
  await expect(header(page, "Stock")).toHaveAttribute("aria-sort", "none");
  await expect(await columnValues(page, "price")).toEqual([
    "$120.00",
    "$68.00",
    "$42.00",
    "$15.00",
    "$9.50",
    "$7.00",
  ]);

  await page.reload();

  await expect(page).toHaveURL("/?sort=price&dir=desc");
  await expect(header(page, "Price")).toHaveAttribute("aria-sort", "descending");
  await expect(await columnValues(page, "price")).toEqual([
    "$120.00",
    "$68.00",
    "$42.00",
    "$15.00",
    "$9.50",
    "$7.00",
  ]);
});

test("marks zero-stock rows with an out of stock badge", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("tbody tr", { hasText: "Bellows" }).getByText("Out of stock")).toBeVisible();
  await expect(page.locator("tbody tr", { hasText: "Emery cloth" }).getByText("Out of stock")).toBeVisible();
  await expect(page.getByText("Out of stock")).toHaveCount(2);
});

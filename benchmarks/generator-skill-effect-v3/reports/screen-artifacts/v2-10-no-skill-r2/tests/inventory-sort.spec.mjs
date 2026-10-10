import { expect, test } from "@playwright/test";

const names = (page) => page.locator("#iv-rows tr td:first-child");
const column = (page, n) => page.locator(`#iv-rows tr td:nth-child(${n})`);
const header = (page, label) => page.getByRole("columnheader", { name: label });
const sortButton = (page, label) => page.getByRole("button", { name: label, exact: true });

async function expectAriaSort(page, expected) {
  for (const [label, value] of Object.entries(expected)) {
    await expect(header(page, label)).toHaveAttribute("aria-sort", value);
  }
}

const PRICE_ASC = ["Emery cloth", "Froe", "Chisel set", "Bellows", "Drawknife", "Anvil"];
const STOCK_ASC = ["Bellows", "Emery cloth", "Drawknife", "Anvil", "Froe", "Chisel set"];

test("starts unsorted with every header aria-sort none", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#iv-rows tr")).toHaveCount(6);
  await expectAriaSort(page, { Name: "none", Price: "none", Stock: "none" });
  expect(new URL(page.url()).search).toBe("");
});

test("clicking a header sorts ascending, clicking again descending", async ({ page }) => {
  await page.goto("/");
  await sortButton(page, "Name").click();
  await expect(names(page)).toContainText(
    ["Anvil", "Bellows", "Chisel set", "Drawknife", "Emery cloth", "Froe"],
  );
  await expectAriaSort(page, { Name: "ascending", Price: "none", Stock: "none" });

  await sortButton(page, "Name").click();
  await expect(names(page)).toContainText(
    ["Froe", "Emery cloth", "Drawknife", "Chisel set", "Bellows", "Anvil"],
  );
  await expectAriaSort(page, { Name: "descending", Price: "none", Stock: "none" });
});

test("switching columns resets to ascending and updates aria-sort", async ({ page }) => {
  await page.goto("/");
  await sortButton(page, "Name").click();
  await sortButton(page, "Name").click();
  await sortButton(page, "Price").click();
  await expectAriaSort(page, { Name: "none", Price: "ascending", Stock: "none" });
  await expect(names(page)).toContainText(PRICE_ASC);
});

test("price sorts numerically, not as text", async ({ page }) => {
  await page.goto("/");
  await sortButton(page, "Price").click();
  // Text order would put $120.00 first and $9.50 last.
  await expect(column(page, 2)).toHaveText(
    ["$7.00", "$9.50", "$15.00", "$42.00", "$68.00", "$120.00"],
  );
  await sortButton(page, "Price").click();
  await expect(column(page, 2)).toHaveText(
    ["$120.00", "$68.00", "$42.00", "$15.00", "$9.50", "$7.00"],
  );
});

test("stock sorts numerically, not as text", async ({ page }) => {
  await page.goto("/");
  await sortButton(page, "Stock").click();
  await expect(column(page, 3)).toHaveText(["0", "0", "1", "2", "6", "14"]);
  await sortButton(page, "Stock").click();
  await expect(column(page, 3)).toHaveText(["14", "6", "2", "1", "0", "0"]);
});

test("the sort is mirrored in the URL", async ({ page }) => {
  await page.goto("/");
  await sortButton(page, "Price").click();
  await expect(page).toHaveURL(/\?sort=price&dir=asc$/);
  await sortButton(page, "Price").click();
  await expect(page).toHaveURL(/\?sort=price&dir=desc$/);
});

test("reloading keeps the sort order and header state", async ({ page }) => {
  await page.goto("/");
  await sortButton(page, "Price").click();
  await sortButton(page, "Price").click();
  await page.reload();
  await expect(column(page, 2)).toHaveText(
    ["$120.00", "$68.00", "$42.00", "$15.00", "$9.50", "$7.00"],
  );
  await expectAriaSort(page, { Name: "none", Price: "descending", Stock: "none" });
});

test("opening a sorted URL directly shows the order and header state", async ({ page }) => {
  await page.goto("/?sort=stock&dir=asc");
  await expect(names(page)).toContainText(STOCK_ASC);
  await expectAriaSort(page, { Name: "none", Price: "none", Stock: "ascending" });

  await page.goto("/?sort=price&dir=desc");
  await expect(names(page)).toContainText([...PRICE_ASC].reverse());
  await expectAriaSort(page, { Name: "none", Price: "descending", Stock: "none" });
});

test("only rows with zero stock carry the Out of stock badge", async ({ page }) => {
  await page.goto("/");
  const badges = page.locator("#iv-rows .badge");
  await expect(badges).toHaveText(["Out of stock", "Out of stock"]);
  for (const name of ["Bellows", "Emery cloth"]) {
    await expect(page.getByRole("row", { name: new RegExp(`^${name}`) })).toContainText("Out of stock");
  }
  for (const name of ["Anvil", "Chisel set", "Drawknife", "Froe"]) {
    await expect(page.getByRole("row", { name: new RegExp(`^${name}`) })).not.toContainText("Out of stock");
  }
});

test("the badge stays with its row after sorting", async ({ page }) => {
  await page.goto("/?sort=stock&dir=asc");
  const rows = page.locator("#iv-rows tr");
  await expect(rows.nth(0)).toContainText("Out of stock");
  await expect(rows.nth(1)).toContainText("Out of stock");
  await expect(rows.nth(2)).not.toContainText("Out of stock");
});

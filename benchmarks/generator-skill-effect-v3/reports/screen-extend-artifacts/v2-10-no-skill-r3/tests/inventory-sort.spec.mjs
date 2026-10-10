import { expect, test } from "@playwright/test";

const columns = ["Name", "Price", "Stock"];

const names = (page) => page.locator("#iv-rows tr td:first-child").evaluateAll(
  (cells) => cells.map((td) => td.firstChild.textContent.trim()),
);

const column = (page, index) => page.locator(`#iv-rows tr td:nth-child(${index})`).allTextContents();

const header = (page, name) => page.getByRole("columnheader", { name });

async function expectSortState(page, active, value) {
  for (const name of columns) {
    await expect(header(page, name)).toHaveAttribute("aria-sort", name === active ? value : "none");
  }
}

test.describe("inventory sorting", () => {
  test("starts unsorted with every header at aria-sort none", async ({ page }) => {
    await page.goto("/");
    await expectSortState(page, null);
    expect(await names(page)).toEqual(["Anvil", "Bellows", "Chisel set", "Drawknife", "Emery cloth", "Froe"]);
    expect(new URL(page.url()).search).toBe("");
  });

  test("clicking Name sorts ascending, then descending", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Name" }).click();
    expect(await names(page)).toEqual(["Anvil", "Bellows", "Chisel set", "Drawknife", "Emery cloth", "Froe"]);
    await expectSortState(page, "Name", "ascending");

    await page.getByRole("button", { name: "Name" }).click();
    expect(await names(page)).toEqual(["Froe", "Emery cloth", "Drawknife", "Chisel set", "Bellows", "Anvil"]);
    await expectSortState(page, "Name", "descending");
  });

  test("Price sorts numerically, not as text", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Price" }).click();
    // A text sort would put $120.00 first and $9.50 last.
    expect(await column(page, 2)).toEqual(["$7.00", "$9.50", "$15.00", "$42.00", "$68.00", "$120.00"]);
    await expectSortState(page, "Price", "ascending");

    await page.getByRole("button", { name: "Price" }).click();
    expect(await column(page, 2)).toEqual(["$120.00", "$68.00", "$42.00", "$15.00", "$9.50", "$7.00"]);
    await expectSortState(page, "Price", "descending");
  });

  test("Stock sorts numerically, not as text", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Stock" }).click();
    expect(await column(page, 3)).toEqual(["0", "0", "1", "2", "6", "14"]);
    await expectSortState(page, "Stock", "ascending");

    await page.getByRole("button", { name: "Stock" }).click();
    expect(await column(page, 3)).toEqual(["14", "6", "2", "1", "0", "0"]);
    await expectSortState(page, "Stock", "descending");
  });

  test("switching columns resets to ascending and clears the previous header", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Price" }).click();
    await page.getByRole("button", { name: "Price" }).click();
    await expectSortState(page, "Price", "descending");

    await page.getByRole("button", { name: "Stock" }).click();
    await expectSortState(page, "Stock", "ascending");
    await expect(page).toHaveURL(/\?sort=stock&dir=asc$/);
  });

  test("the sort is mirrored in the URL", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Price" }).click();
    await expect(page).toHaveURL(/\?sort=price&dir=asc$/);
    await page.getByRole("button", { name: "Price" }).click();
    await expect(page).toHaveURL(/\?sort=price&dir=desc$/);
  });

  test("opening a sorted URL directly shows the order and header state", async ({ page }) => {
    await page.goto("/?sort=price&dir=desc");
    expect(await column(page, 2)).toEqual(["$120.00", "$68.00", "$42.00", "$15.00", "$9.50", "$7.00"]);
    await expectSortState(page, "Price", "descending");
  });

  test("reloading keeps the sort", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Stock" }).click();
    await page.getByRole("button", { name: "Stock" }).click();
    await page.reload();
    expect(await column(page, 3)).toEqual(["14", "6", "2", "1", "0", "0"]);
    await expectSortState(page, "Stock", "descending");
    await expect(page).toHaveURL(/\?sort=stock&dir=desc$/);
  });

  test("zero-stock rows carry an Out of stock badge", async ({ page }) => {
    await page.goto("/");
    const badges = page.locator("#iv-rows .badge");
    await expect(badges).toHaveCount(2);
    await expect(badges).toHaveText(["Out of stock", "Out of stock"]);
    await expect(page.getByRole("row", { name: /Bellows/ })).toContainText("Out of stock");
    await expect(page.getByRole("row", { name: /Emery cloth/ })).toContainText("Out of stock");
    await expect(page.getByRole("row", { name: /Anvil/ })).not.toContainText("Out of stock");
  });

  test("the badge follows its row when sorted", async ({ page }) => {
    await page.goto("/?sort=stock&dir=asc");
    const rows = page.locator("#iv-rows tr");
    await expect(rows.nth(0)).toContainText("Out of stock");
    await expect(rows.nth(1)).toContainText("Out of stock");
    await expect(rows.nth(2)).not.toContainText("Out of stock");
  });
});

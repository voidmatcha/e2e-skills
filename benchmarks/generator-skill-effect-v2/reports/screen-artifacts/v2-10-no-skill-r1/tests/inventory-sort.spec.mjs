import { expect, test } from "@playwright/test";

const header = (page, name) => page.getByRole("columnheader", { name });
const names = async (page) =>
  (await page.locator("#iv-rows tr td:first-child").allTextContents()).map((t) =>
    t.replace("Out of stock", "").trim(),
  );
const column = async (page, n) => page.locator(`#iv-rows tr td:nth-child(${n})`).allTextContents();

async function expectAriaSort(page, active, value) {
  for (const name of ["Name", "Price", "Stock"]) {
    await expect(header(page, name)).toHaveAttribute("aria-sort", name === active ? value : "none");
  }
}

test("starts unsorted with every header aria-sort none", async ({ page }) => {
  await page.goto("/");
  await expectAriaSort(page, null);
  expect(await names(page)).toEqual(["Anvil", "Bellows", "Chisel set", "Drawknife", "Emery cloth", "Froe"]);
});

test("clicking Name sorts ascending, then descending", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Name" }).click();
  expect(await names(page)).toEqual(["Anvil", "Bellows", "Chisel set", "Drawknife", "Emery cloth", "Froe"]);
  await expectAriaSort(page, "Name", "ascending");

  await page.getByRole("button", { name: "Name" }).click();
  expect(await names(page)).toEqual(["Froe", "Emery cloth", "Drawknife", "Chisel set", "Bellows", "Anvil"]);
  await expectAriaSort(page, "Name", "descending");
});

test("Price sorts numerically, not as text", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Price" }).click();
  expect(await column(page, 2)).toEqual(["$7.00", "$9.50", "$15.00", "$42.00", "$68.00", "$120.00"]);
  await expectAriaSort(page, "Price", "ascending");

  await page.getByRole("button", { name: "Price" }).click();
  expect(await column(page, 2)).toEqual(["$120.00", "$68.00", "$42.00", "$15.00", "$9.50", "$7.00"]);
  await expectAriaSort(page, "Price", "descending");
});

test("Stock sorts numerically, not as text", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Stock" }).click();
  expect(await column(page, 3)).toEqual(["0", "0", "1", "2", "6", "14"]);
  await expectAriaSort(page, "Stock", "ascending");

  await page.getByRole("button", { name: "Stock" }).click();
  expect(await column(page, 3)).toEqual(["14", "6", "2", "1", "0", "0"]);
  await expectAriaSort(page, "Stock", "descending");
});

test("switching columns resets to ascending and clears the previous header", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Price" }).click();
  await page.getByRole("button", { name: "Price" }).click();
  await page.getByRole("button", { name: "Stock" }).click();
  await expectAriaSort(page, "Stock", "ascending");
  await expect(page).toHaveURL(/\?sort=stock&dir=asc$/);
});

test("the sort is mirrored in the URL", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Price" }).click();
  await expect(page).toHaveURL(/\?sort=price&dir=asc$/);
  await page.getByRole("button", { name: "Price" }).click();
  await expect(page).toHaveURL(/\?sort=price&dir=desc$/);
});

test("reloading keeps the order and header state", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Price" }).click();
  await page.getByRole("button", { name: "Price" }).click();
  await page.reload();
  expect(await column(page, 2)).toEqual(["$120.00", "$68.00", "$42.00", "$15.00", "$9.50", "$7.00"]);
  await expectAriaSort(page, "Price", "descending");
});

test("opening a sorted URL directly shows the same order and header state", async ({ page }) => {
  await page.goto("/?sort=stock&dir=desc");
  expect(await column(page, 3)).toEqual(["14", "6", "2", "1", "0", "0"]);
  await expectAriaSort(page, "Stock", "descending");

  await page.goto("/?sort=name&dir=asc");
  expect((await names(page))[0]).toBe("Anvil");
  await expectAriaSort(page, "Name", "ascending");
});

test("only rows with zero stock carry the Out of stock badge", async ({ page }) => {
  await page.goto("/");
  const badged = page.locator("#iv-rows tr", { has: page.getByText("Out of stock") });
  await expect(badged).toHaveCount(2);
  await expect(badged.nth(0)).toContainText("Bellows");
  await expect(badged.nth(1)).toContainText("Emery cloth");
  await expect(page.getByText("Out of stock")).toHaveCount(2);
});

test("the badge follows its row when sorted", async ({ page }) => {
  await page.goto("/?sort=stock&dir=asc");
  const rows = page.locator("#iv-rows tr");
  await expect(rows.nth(0)).toContainText("Out of stock");
  await expect(rows.nth(1)).toContainText("Out of stock");
  await expect(rows.nth(2)).not.toContainText("Out of stock");
});

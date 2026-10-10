import { expect, test } from "@playwright/test";

const header = (page, name) => page.getByRole("columnheader", { name });
const sortButton = (page, name) => page.getByRole("button", { name, exact: true });
const column = (page, index) => page.locator("#iv-rows tr").evaluateAll(
  (trs, i) => trs.map((tr) => tr.children[i].firstChild.textContent.trim()),
  index,
);

const expectAria = async (page, expected) => {
  for (const [name, value] of Object.entries(expected)) {
    await expect(header(page, name)).toHaveAttribute("aria-sort", value);
  }
};

const NAMES_ASC = ["Anvil", "Bellows", "Chisel set", "Drawknife", "Emery cloth", "Froe"];
const PRICES_ASC = ["$7.00", "$9.50", "$15.00", "$42.00", "$68.00", "$120.00"];

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#iv-rows tr")).toHaveCount(6);
});

test("starts unsorted with every header at aria-sort none", async ({ page }) => {
  await expectAria(page, { Name: "none", Price: "none", Stock: "none" });
  expect(new URL(page.url()).search).toBe("");
});

test("clicking a header sorts ascending, clicking again sorts descending", async ({ page }) => {
  await sortButton(page, "Name").click();
  expect(await column(page, 0)).toEqual(NAMES_ASC);
  await expectAria(page, { Name: "ascending", Price: "none", Stock: "none" });

  await sortButton(page, "Name").click();
  expect(await column(page, 0)).toEqual([...NAMES_ASC].reverse());
  await expectAria(page, { Name: "descending", Price: "none", Stock: "none" });
});

test("price sorts numerically, not as text", async ({ page }) => {
  await sortButton(page, "Price").click();
  expect(await column(page, 1)).toEqual(PRICES_ASC);
  await expectAria(page, { Name: "none", Price: "ascending", Stock: "none" });

  await sortButton(page, "Price").click();
  expect(await column(page, 1)).toEqual([...PRICES_ASC].reverse());
  await expectAria(page, { Name: "none", Price: "descending", Stock: "none" });
});

test("stock sorts numerically, not as text", async ({ page }) => {
  await sortButton(page, "Stock").click();
  expect(await column(page, 2)).toEqual(["0", "0", "1", "2", "6", "14"]);
  await expectAria(page, { Name: "none", Price: "none", Stock: "ascending" });

  await sortButton(page, "Stock").click();
  expect(await column(page, 2)).toEqual(["14", "6", "2", "1", "0", "0"]);
  await expectAria(page, { Name: "none", Price: "none", Stock: "descending" });
});

test("switching columns starts ascending and resets the previous header", async ({ page }) => {
  await sortButton(page, "Price").click();
  await sortButton(page, "Price").click();
  await sortButton(page, "Stock").click();
  await expectAria(page, { Name: "none", Price: "none", Stock: "ascending" });
  expect(await column(page, 2)).toEqual(["0", "0", "1", "2", "6", "14"]);
  expect(page.url()).toContain("sort=stock&dir=asc");
});

test("the sort is mirrored in the URL", async ({ page }) => {
  await sortButton(page, "Price").click();
  expect(new URL(page.url()).search).toBe("?sort=price&dir=asc");
  await sortButton(page, "Price").click();
  expect(new URL(page.url()).search).toBe("?sort=price&dir=desc");
});

test("reloading keeps the sort order and header state", async ({ page }) => {
  await sortButton(page, "Price").click();
  await sortButton(page, "Price").click();
  await page.reload();
  expect(await column(page, 1)).toEqual([...PRICES_ASC].reverse());
  await expectAria(page, { Name: "none", Price: "descending", Stock: "none" });
});

test("opening a sorted URL directly shows the order and header state", async ({ page }) => {
  await page.goto("/?sort=stock&dir=desc");
  expect(await column(page, 2)).toEqual(["14", "6", "2", "1", "0", "0"]);
  await expectAria(page, { Name: "none", Price: "none", Stock: "descending" });

  await page.goto("/?sort=name&dir=asc");
  expect(await column(page, 0)).toEqual(NAMES_ASC);
  await expectAria(page, { Name: "ascending", Price: "none", Stock: "none" });
});

test("only zero-stock rows carry the Out of stock badge", async ({ page }) => {
  const rows = page.locator("#iv-rows tr");
  await expect(page.getByText("Out of stock")).toHaveCount(2);
  for (const name of ["Bellows", "Emery cloth"]) {
    await expect(rows.filter({ hasText: name }).getByText("Out of stock")).toBeVisible();
  }
  for (const name of ["Anvil", "Chisel set", "Drawknife", "Froe"]) {
    await expect(rows.filter({ hasText: name }).getByText("Out of stock")).toHaveCount(0);
  }
});

test("badges follow their rows when sorted", async ({ page }) => {
  await page.goto("/?sort=stock&dir=asc");
  const rows = page.locator("#iv-rows tr");
  await expect(rows.nth(0).getByText("Out of stock")).toBeVisible();
  await expect(rows.nth(1).getByText("Out of stock")).toBeVisible();
  await expect(page.getByText("Out of stock")).toHaveCount(2);
});

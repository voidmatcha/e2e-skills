import { expect, test } from "@playwright/test";

const list = (page) => page.getByRole("list", { name: "Orders" }).getByRole("listitem");
const status = (page) => page.getByLabel("Status");
const search = (page) => page.getByLabel("Search");
const count = (page) => page.locator("#or-count");

async function expectOrders(page, ids) {
  await expect(list(page)).toHaveCount(ids.length);
  for (const [i, id] of ids.entries()) {
    await expect(list(page).nth(i)).toContainText(`#${id}`);
  }
  await expect(count(page)).toHaveText(ids.length === 1 ? "1 order" : `${ids.length} orders`);
}

const ALL = ["1001", "1002", "1003", "1010", "1011", "1020", "2001", "2010"];

test("shows every order with no filters", async ({ page }) => {
  await page.goto("/");
  await expectOrders(page, ALL);
  await expect(status(page)).toHaveValue("");
  await expect(search(page)).toHaveValue("");
});

test("status filter narrows the list and the count", async ({ page }) => {
  await page.goto("/");
  await status(page).selectOption("shipped");
  await expectOrders(page, ["1002", "1010", "1020"]);
  await status(page).selectOption("refunded");
  await expectOrders(page, ["1003", "2010"]);
});

test("search matches order numbers containing the digits", async ({ page }) => {
  await page.goto("/");
  await search(page).fill("101");
  await expectOrders(page, ["1010", "1011"]);
  await search(page).fill("2");
  await expectOrders(page, ["1002", "1020", "2001", "2010"]);
  await search(page).fill("1011");
  await expectOrders(page, ["1011"]);
});

test("search with no match shows an empty list", async ({ page }) => {
  await page.goto("/");
  await search(page).fill("9999");
  await expectOrders(page, []);
});

test("status and search apply together", async ({ page }) => {
  await page.goto("/");
  await status(page).selectOption("shipped");
  await search(page).fill("101");
  await expectOrders(page, ["1010"]);
  await status(page).selectOption("paid");
  await expectOrders(page, ["1011"]);
  await status(page).selectOption("refunded");
  await expectOrders(page, []);
});

test("filters are mirrored in the URL", async ({ page }) => {
  await page.goto("/");
  await status(page).selectOption("shipped");
  await search(page).fill("101");
  await expect(page).toHaveURL(/\?(status=shipped&q=101)$/);
});

test("reload keeps the filtered list and controls", async ({ page }) => {
  await page.goto("/");
  await status(page).selectOption("shipped");
  await search(page).fill("101");
  await page.reload();
  await expect(status(page)).toHaveValue("shipped");
  await expect(search(page)).toHaveValue("101");
  await expectOrders(page, ["1010"]);
});

test("opening a filtered URL directly applies the filters", async ({ page }) => {
  await page.goto("/?status=shipped&q=101");
  await expect(status(page)).toHaveValue("shipped");
  await expect(search(page)).toHaveValue("101");
  await expectOrders(page, ["1010"]);
});

test("opening a URL with only one filter applies it", async ({ page }) => {
  await page.goto("/?status=paid");
  await expect(search(page)).toHaveValue("");
  await expectOrders(page, ["1001", "1011", "2001"]);
  await page.goto("/?q=200");
  await expect(status(page)).toHaveValue("");
  await expectOrders(page, ["2001"]);
});

test("clear filters resets both controls, the list and the URL", async ({ page }) => {
  await page.goto("/?status=shipped&q=101");
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(status(page)).toHaveValue("");
  await expect(search(page)).toHaveValue("");
  await expectOrders(page, ALL);
  await expect(page).not.toHaveURL(/\?/);
  await page.reload();
  await expectOrders(page, ALL);
});

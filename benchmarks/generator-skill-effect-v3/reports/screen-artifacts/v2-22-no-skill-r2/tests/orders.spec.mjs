import { expect, test } from "@playwright/test";

const ALL = ["1001", "1002", "1003", "1010", "1011", "1020", "2001", "2010"];

const status = (page) => page.getByLabel("Status");
const search = (page) => page.getByLabel("Search");

async function expectOrders(page, ids) {
  const items = page.getByRole("list", { name: "Orders" }).getByRole("listitem");
  await expect(items).toHaveCount(ids.length);
  await expect(items).toHaveText(ids.map((id) => new RegExp(`^#${id} `)));
  await expect(page.locator("#or-count")).toHaveText(ids.length === 1 ? "1 order" : `${ids.length} orders`);
}

test("shows all orders by default", async ({ page }) => {
  await page.goto("/");
  await expectOrders(page, ALL);
  await expect(status(page)).toHaveValue("");
  await expect(search(page)).toHaveValue("");
});

test("status filter narrows the list", async ({ page }) => {
  await page.goto("/");
  await status(page).selectOption("shipped");
  await expectOrders(page, ["1002", "1010", "1020"]);
  await expect(page).toHaveURL(/\?status=shipped$/);
});

test("search matches order numbers containing the digits", async ({ page }) => {
  await page.goto("/");
  await search(page).fill("010");
  await expectOrders(page, ["1010", "2010"]);
  await search(page).fill("2010");
  await expectOrders(page, ["2010"]);
  await expect(page).toHaveURL(/\?q=2010$/);
});

test("search with no match shows zero orders", async ({ page }) => {
  await page.goto("/");
  await search(page).fill("9999");
  await expectOrders(page, []);
});

test("status and search apply together", async ({ page }) => {
  await page.goto("/");
  await search(page).fill("101");
  await expectOrders(page, ["1010", "1011"]);
  await status(page).selectOption("shipped");
  await expectOrders(page, ["1010"]);
  await status(page).selectOption("paid");
  await expectOrders(page, ["1011"]);
  await status(page).selectOption("refunded");
  await expectOrders(page, []);
  await expect(page).toHaveURL(/\?status=refunded&q=101$/);
});

test("reload keeps the filters and the list", async ({ page }) => {
  await page.goto("/");
  await status(page).selectOption("shipped");
  await search(page).fill("101");
  await page.reload();
  await expect(status(page)).toHaveValue("shipped");
  await expect(search(page)).toHaveValue("101");
  await expectOrders(page, ["1010"]);
});

test("opening a filtered URL directly sets controls and list", async ({ page }) => {
  await page.goto("/?status=refunded&q=010");
  await expect(status(page)).toHaveValue("refunded");
  await expect(search(page)).toHaveValue("010");
  await expectOrders(page, ["2010"]);
});

test("clear filters resets controls, URL and list", async ({ page }) => {
  await page.goto("/?status=shipped&q=101");
  await expectOrders(page, ["1010"]);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(status(page)).toHaveValue("");
  await expect(search(page)).toHaveValue("");
  await expectOrders(page, ALL);
  await expect(page).not.toHaveURL(/\?/);
  await page.reload();
  await expectOrders(page, ALL);
});

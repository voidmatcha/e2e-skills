import { expect, test } from "@playwright/test";

const ALL = ["1001", "1002", "1003", "1010", "1011", "1020", "2001", "2010"];

async function expectOrders(page, ids) {
  const items = page.getByRole("list", { name: "Orders" }).getByRole("listitem");
  await expect(items).toHaveCount(ids.length);
  for (const [i, id] of ids.entries()) {
    await expect(items.nth(i)).toContainText(`#${id}`);
  }
  await expect(page.locator("#or-count")).toHaveText(ids.length === 1 ? "1 order" : `${ids.length} orders`);
}

const status = (page) => page.getByLabel("Status");
const search = (page) => page.getByLabel("Search");

test("lists all orders by default", async ({ page }) => {
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
  await search(page).fill("10");
  await expectOrders(page, ["1001", "1002", "1003", "1010", "1011", "1020", "2010"]);
  await expect(page).toHaveURL(/\?q=10$/);
});

test("status and search apply together", async ({ page }) => {
  await page.goto("/");
  await search(page).fill("101");
  await expectOrders(page, ["1010", "1011"]);
  await status(page).selectOption("shipped");
  await expectOrders(page, ["1010"]);
  await expect(page).toHaveURL(/\?status=shipped&q=101$/);
  await status(page).selectOption("refunded");
  await expectOrders(page, []);
});

test("shows 0 orders when nothing matches", async ({ page }) => {
  await page.goto("/");
  await search(page).fill("9999");
  await expectOrders(page, []);
});

test("opening a filtered URL applies the filters and sets the controls", async ({ page }) => {
  await page.goto("/?status=shipped&q=101");
  await expectOrders(page, ["1010"]);
  await expect(status(page)).toHaveValue("shipped");
  await expect(search(page)).toHaveValue("101");
});

test("reload keeps the filtered list", async ({ page }) => {
  await page.goto("/");
  await status(page).selectOption("paid");
  await search(page).fill("20");
  await expectOrders(page, ["2001"]);
  await page.reload();
  await expectOrders(page, ["2001"]);
  await expect(status(page)).toHaveValue("paid");
  await expect(search(page)).toHaveValue("20");
});

test("clear filters resets controls, list and URL", async ({ page }) => {
  await page.goto("/?status=shipped&q=101");
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(status(page)).toHaveValue("");
  await expect(search(page)).toHaveValue("");
  await expectOrders(page, ALL);
  await expect(page).not.toHaveURL(/\?/);
  await page.reload();
  await expectOrders(page, ALL);
});

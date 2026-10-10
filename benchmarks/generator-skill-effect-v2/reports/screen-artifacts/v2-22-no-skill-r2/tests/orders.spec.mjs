import { expect, test } from "@playwright/test";

const ALL = ["1001", "1002", "1003", "1010", "1011", "1020", "2001", "2010"];

const status = (page) => page.getByLabel("Status");
const search = (page) => page.getByLabel("Search");

async function expectOrders(page, ids) {
  const items = page.getByRole("list", { name: "Orders" }).getByRole("listitem");
  await expect(items).toHaveCount(ids.length);
  for (const [i, id] of ids.entries()) {
    await expect(items.nth(i)).toContainText(`#${id} `);
  }
  await expect(page.locator("#or-count")).toHaveText(ids.length === 1 ? "1 order" : `${ids.length} orders`);
}

test("lists every order with no filters", async ({ page }) => {
  await page.goto("/");
  await expectOrders(page, ALL);
  await expect(status(page)).toHaveValue("");
  await expect(search(page)).toHaveValue("");
});

test("status filter narrows the list", async ({ page }) => {
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
  await search(page).fill("10");
  await expectOrders(page, ["1001", "1002", "1003", "1010", "1011", "1020", "2010"]);
});

test("status and search must both hold", async ({ page }) => {
  await page.goto("/");
  await status(page).selectOption("shipped");
  await search(page).fill("101");
  await expectOrders(page, ["1010"]);
  await status(page).selectOption("paid");
  await expectOrders(page, ["1011"]);
});

test("shows 0 orders when nothing matches", async ({ page }) => {
  await page.goto("/");
  await status(page).selectOption("paid");
  await search(page).fill("201");
  await expectOrders(page, []);
});

test("filters are mirrored in the URL", async ({ page }) => {
  await page.goto("/");
  await status(page).selectOption("shipped");
  await search(page).fill("101");
  await expect(page).toHaveURL(/[?&]status=shipped/);
  await expect(page).toHaveURL(/[?&]q=101/);
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
  await page.goto("/?status=paid&q=100");
  await expect(status(page)).toHaveValue("paid");
  await expect(search(page)).toHaveValue("100");
  await expectOrders(page, ["1001"]);
});

test("opening a URL with only one filter applies it", async ({ page }) => {
  await page.goto("/?q=2");
  await expect(status(page)).toHaveValue("");
  await expect(search(page)).toHaveValue("2");
  await expectOrders(page, ["1002", "1020", "2001", "2010"]);
});

test("clear filters resets controls, URL and list", async ({ page }) => {
  await page.goto("/?status=shipped&q=101");
  await expectOrders(page, ["1010"]);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(status(page)).toHaveValue("");
  await expect(search(page)).toHaveValue("");
  await expectOrders(page, ALL);
  await expect(page).not.toHaveURL(/[?&](status|q)=/);
  await page.reload();
  await expectOrders(page, ALL);
});

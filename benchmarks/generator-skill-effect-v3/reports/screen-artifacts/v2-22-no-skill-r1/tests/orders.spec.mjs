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

test("shows every order by default", async ({ page }) => {
  await page.goto("/");
  await expectOrders(page, ALL);
  await expect(page.getByLabel("Status")).toHaveValue("");
  await expect(page.getByLabel("Search")).toHaveValue("");
});

test("status filter narrows the list", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Status").selectOption("shipped");
  await expectOrders(page, ["1002", "1010", "1020"]);
  await expect(page).toHaveURL(/\?status=shipped$/);
});

test("search matches order numbers containing the digits", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Search").fill("101");
  await expectOrders(page, ["1010", "1011"]);
  await page.getByLabel("Search").fill("010");
  await expectOrders(page, ["1010", "2010"]);
  await expect(page).toHaveURL(/\?q=010$/);
});

test("status and search apply together", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Status").selectOption("shipped");
  await page.getByLabel("Search").fill("101");
  await expectOrders(page, ["1010"]);
  await expect(page).toHaveURL(/\?status=shipped&q=101$/);
  await page.getByLabel("Search").fill("10");
  await expectOrders(page, ["1002", "1010", "1020"]);
});

test("no matches shows 0 orders", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Status").selectOption("refunded");
  await page.getByLabel("Search").fill("1001");
  await expectOrders(page, []);
});

test("opening a filtered URL restores list and controls", async ({ page }) => {
  await page.goto("/?status=shipped&q=101");
  await expect(page.getByLabel("Status")).toHaveValue("shipped");
  await expect(page.getByLabel("Search")).toHaveValue("101");
  await expectOrders(page, ["1010"]);
});

test("reload keeps the filtered list", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Status").selectOption("paid");
  await page.getByLabel("Search").fill("200");
  await expectOrders(page, ["2001"]);
  await page.reload();
  await expect(page.getByLabel("Status")).toHaveValue("paid");
  await expect(page.getByLabel("Search")).toHaveValue("200");
  await expectOrders(page, ["2001"]);
});

test("clear filters resets controls, list and URL", async ({ page }) => {
  await page.goto("/?status=shipped&q=101");
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByLabel("Status")).toHaveValue("");
  await expect(page.getByLabel("Search")).toHaveValue("");
  await expectOrders(page, ALL);
  await expect(page).not.toHaveURL(/\?/);
  await page.reload();
  await expectOrders(page, ALL);
});

import { expect, test } from "@playwright/test";

const allOrderIds = ["1001", "1002", "1003", "1010", "1011", "1020", "2001", "2010"];

const orderList = (page) => page.getByRole("list", { name: "Orders" });
const orderItems = (page) => orderList(page).getByRole("listitem");
const statusFilter = (page) => page.getByLabel("Status");
const searchBox = (page) => page.getByLabel("Search");
const countLine = (page) => page.locator("#or-count");

async function expectVisibleOrderIds(page, expectedIds) {
  await expect(orderItems(page)).toHaveCount(expectedIds.length);
  await expect(orderItems(page)).toHaveText(expectedIds.map((id) => new RegExp(`^#${id} `)));
}

test("shows all orders by default", async ({ page }) => {
  await page.goto("/");

  await expect(statusFilter(page)).toHaveValue("");
  await expect(searchBox(page)).toHaveValue("");
  await expectVisibleOrderIds(page, allOrderIds);
  await expect(countLine(page)).toHaveText("8 orders");
});

test("combines status and order-number search filters", async ({ page }) => {
  await page.goto("/");

  await statusFilter(page).selectOption("shipped");
  await expectVisibleOrderIds(page, ["1002", "1010", "1020"]);
  await expect(countLine(page)).toHaveText("3 orders");
  await expect(page).toHaveURL("/?status=shipped");

  await searchBox(page).fill("101");
  await expectVisibleOrderIds(page, ["1010"]);
  await expect(countLine(page)).toHaveText("1 order");
  await expect(page).toHaveURL("/?status=shipped&q=101");
});

test("loads and reloads with filters from the URL", async ({ page }) => {
  await page.goto("/?status=refunded&q=10");

  await expect(statusFilter(page)).toHaveValue("refunded");
  await expect(searchBox(page)).toHaveValue("10");
  await expectVisibleOrderIds(page, ["1003", "2010"]);
  await expect(countLine(page)).toHaveText("2 orders");

  await page.reload();

  await expect(statusFilter(page)).toHaveValue("refunded");
  await expect(searchBox(page)).toHaveValue("10");
  await expectVisibleOrderIds(page, ["1003", "2010"]);
  await expect(countLine(page)).toHaveText("2 orders");
});

test("clear filters restores every order", async ({ page }) => {
  await page.goto("/?status=paid&q=20");

  await expectVisibleOrderIds(page, ["2001"]);
  await page.getByRole("button", { name: "Clear filters" }).click();

  await expect(statusFilter(page)).toHaveValue("");
  await expect(searchBox(page)).toHaveValue("");
  await expectVisibleOrderIds(page, allOrderIds);
  await expect(countLine(page)).toHaveText("8 orders");
  await expect(page).toHaveURL("/");
});

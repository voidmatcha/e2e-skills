import { expect, test } from "@playwright/test";

const ALL_ORDERS = [
  "#1001 — Ada — paid",
  "#1002 — Grace — shipped",
  "#1003 — Linus — refunded",
  "#1010 — Margaret — shipped",
  "#1011 — Ken — paid",
  "#1020 — Barbara — shipped",
  "#2001 — Dennis — paid",
  "#2010 — Radia — refunded",
];

const ordersList = (page) => page.getByRole("list", { name: "Orders" });
const orderItems = (page) => ordersList(page).getByRole("listitem");

async function expectOrders(page, expected) {
  await expect(orderItems(page)).toHaveText(expected);
  await expect(page.locator("#or-count")).toHaveText(
    expected.length === 1 ? "1 order" : `${expected.length} orders`,
  );
}

test("shows all orders by default", async ({ page }) => {
  await page.goto("/");

  await expectOrders(page, ALL_ORDERS);
});

test("narrows orders by status and search together", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Status").selectOption("shipped");
  await page.getByLabel("Search").fill("101");

  await expectOrders(page, ["#1010 — Margaret — shipped"]);
  await expect(page.getByLabel("Status")).toHaveValue("shipped");
  await expect(page.getByLabel("Search")).toHaveValue("101");
  await expect(page).toHaveURL(/\/\?status=shipped&q=101$/);
});

test("restores filtered controls and list from the URL", async ({ page }) => {
  await page.goto("/?status=refunded&q=10");

  await expect(page.getByLabel("Status")).toHaveValue("refunded");
  await expect(page.getByLabel("Search")).toHaveValue("10");
  await expectOrders(page, [
    "#1003 — Linus — refunded",
    "#2010 — Radia — refunded",
  ]);

  await page.reload();

  await expect(page.getByLabel("Status")).toHaveValue("refunded");
  await expect(page.getByLabel("Search")).toHaveValue("10");
  await expectOrders(page, [
    "#1003 — Linus — refunded",
    "#2010 — Radia — refunded",
  ]);
});

test("clears both filters and shows every order again", async ({ page }) => {
  await page.goto("/?status=paid&q=10");
  await expectOrders(page, [
    "#1001 — Ada — paid",
    "#1011 — Ken — paid",
  ]);

  await page.getByRole("button", { name: "Clear filters" }).click();

  await expect(page.getByLabel("Status")).toHaveValue("");
  await expect(page.getByLabel("Search")).toHaveValue("");
  await expect(page).toHaveURL("/");
  await expectOrders(page, ALL_ORDERS);
});

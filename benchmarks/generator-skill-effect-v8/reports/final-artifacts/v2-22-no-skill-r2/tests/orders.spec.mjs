import { expect, test } from "@playwright/test";

const orderList = (page) => page.getByRole("list", { name: "Orders" });
const orders = (page) => orderList(page).getByRole("listitem");

async function expectOrders(page, expected) {
  await expect(orders(page)).toHaveText(expected);
  await expect(page.getByText(`${expected.length} ${expected.length === 1 ? "order" : "orders"}`)).toBeVisible();
}

test("shows all orders by default", async ({ page }) => {
  await page.goto("/");

  await expectOrders(page, [
    "#1001 — Ada — paid",
    "#1002 — Grace — shipped",
    "#1003 — Linus — refunded",
    "#1010 — Margaret — shipped",
    "#1011 — Ken — paid",
    "#1020 — Barbara — shipped",
    "#2001 — Dennis — paid",
    "#2010 — Radia — refunded",
  ]);
});

test("combines status and order-number search filters", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Status").selectOption("shipped");
  await expectOrders(page, [
    "#1002 — Grace — shipped",
    "#1010 — Margaret — shipped",
    "#1020 — Barbara — shipped",
  ]);
  await expect(page).toHaveURL("/?status=shipped");

  await page.getByLabel("Search").fill("101");
  await expectOrders(page, ["#1010 — Margaret — shipped"]);
  await expect(page).toHaveURL("/?status=shipped&q=101");

  await page.getByLabel("Status").selectOption("paid");
  await expectOrders(page, ["#1011 — Ken — paid"]);
  await expect(page).toHaveURL("/?status=paid&q=101");
});

test("loads filters from the URL and keeps them after reload", async ({ page }) => {
  await page.goto("/?status=shipped&q=10");

  await expect(page.getByLabel("Status")).toHaveValue("shipped");
  await expect(page.getByLabel("Search")).toHaveValue("10");
  await expectOrders(page, [
    "#1002 — Grace — shipped",
    "#1010 — Margaret — shipped",
    "#1020 — Barbara — shipped",
  ]);

  await page.reload();

  await expect(page.getByLabel("Status")).toHaveValue("shipped");
  await expect(page.getByLabel("Search")).toHaveValue("10");
  await expectOrders(page, [
    "#1002 — Grace — shipped",
    "#1010 — Margaret — shipped",
    "#1020 — Barbara — shipped",
  ]);
});

test("clear filters resets the controls, URL, and order list", async ({ page }) => {
  await page.goto("/?status=paid&q=20");

  await expectOrders(page, ["#2001 — Dennis — paid"]);

  await page.getByRole("button", { name: "Clear filters" }).click();

  await expect(page.getByLabel("Status")).toHaveValue("");
  await expect(page.getByLabel("Search")).toHaveValue("");
  await expect(page).toHaveURL("/");
  await expectOrders(page, [
    "#1001 — Ada — paid",
    "#1002 — Grace — shipped",
    "#1003 — Linus — refunded",
    "#1010 — Margaret — shipped",
    "#1011 — Ken — paid",
    "#1020 — Barbara — shipped",
    "#2001 — Dennis — paid",
    "#2010 — Radia — refunded",
  ]);
});

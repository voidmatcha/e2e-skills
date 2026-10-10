import { expect, test } from "@playwright/test";

const allOrders = [
  "#1001 — Ada — paid",
  "#1002 — Grace — shipped",
  "#1003 — Linus — refunded",
  "#1010 — Margaret — shipped",
  "#1011 — Ken — paid",
  "#1020 — Barbara — shipped",
  "#2001 — Dennis — paid",
  "#2010 — Radia — refunded",
];

async function expectOrders(page, orders, countText) {
  await expect(page.getByRole("list", { name: "Orders", exact: true }).getByRole("listitem")).toHaveText(orders);
  await expect(page.getByText(countText, { exact: true })).toBeVisible();
}

test("shows every order by default", async ({ page }) => {
  await page.goto("/");

  await expectOrders(page, allOrders, "8 orders");
});

test("narrows orders by status and order-number search together", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Status").selectOption("shipped");
  await page.getByLabel("Search").fill("101");

  await expect(page).toHaveURL("/?status=shipped&q=101");
  await expectOrders(page, ["#1010 — Margaret — shipped"], "1 order");
});

test("opens filtered URL, keeps controls after reload, and clears filters", async ({ page }) => {
  await page.goto("/?status=refunded&q=10");

  await expect(page.getByLabel("Status")).toHaveValue("refunded");
  await expect(page.getByLabel("Search")).toHaveValue("10");
  await expectOrders(page, ["#1003 — Linus — refunded", "#2010 — Radia — refunded"], "2 orders");

  await page.reload();

  await expect(page.getByLabel("Status")).toHaveValue("refunded");
  await expect(page.getByLabel("Search")).toHaveValue("10");
  await expectOrders(page, ["#1003 — Linus — refunded", "#2010 — Radia — refunded"], "2 orders");

  await page.getByRole("button", { name: "Clear filters", exact: true }).click();

  await expect(page).toHaveURL("/");
  await expect(page.getByLabel("Status")).toHaveValue("");
  await expect(page.getByLabel("Search")).toHaveValue("");
  await expectOrders(page, allOrders, "8 orders");
});

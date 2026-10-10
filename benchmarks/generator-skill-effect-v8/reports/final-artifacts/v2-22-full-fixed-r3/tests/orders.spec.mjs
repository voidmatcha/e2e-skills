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

const orderRows = (page) =>
  page.getByRole("list", { name: /^Orders$/ }).getByRole("listitem");

test("narrows orders by status and search together", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Status").selectOption("shipped");
  await page.getByLabel("Search").fill("101");

  await expect(page).toHaveURL("/?status=shipped&q=101");
  await expect(orderRows(page)).toHaveText(["#1010 — Margaret — shipped"]);
  await expect(page.getByText("1 order")).toBeVisible();
});

test("opens and reloads with filters from the URL", async ({ page }) => {
  await page.goto("/?status=refunded&q=201");

  await expect(page.getByLabel("Status")).toHaveValue("refunded");
  await expect(page.getByLabel("Search")).toHaveValue("201");
  await expect(orderRows(page)).toHaveText(["#2010 — Radia — refunded"]);
  await expect(page.getByText("1 order")).toBeVisible();

  await page.reload();

  await expect(page).toHaveURL("/?status=refunded&q=201");
  await expect(page.getByLabel("Status")).toHaveValue("refunded");
  await expect(page.getByLabel("Search")).toHaveValue("201");
  await expect(orderRows(page)).toHaveText(["#2010 — Radia — refunded"]);
  await expect(page.getByText("1 order")).toBeVisible();
});

test("clears filters and shows every order", async ({ page }) => {
  await page.goto("/?status=shipped&q=101");

  await page.getByRole("button", { name: /^Clear filters$/ }).click();

  await expect(page).toHaveURL("/");
  await expect(page.getByLabel("Status")).toHaveValue("");
  await expect(page.getByLabel("Search")).toHaveValue("");
  await expect(orderRows(page)).toHaveText(allOrders);
  await expect(page.getByText("8 orders")).toBeVisible();
});

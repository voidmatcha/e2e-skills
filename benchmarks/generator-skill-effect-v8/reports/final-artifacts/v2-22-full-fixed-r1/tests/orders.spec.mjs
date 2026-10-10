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

test("narrows orders by status and search together", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Status").selectOption("shipped");
  await page.getByRole("textbox", { name: /^Search$/ }).fill("101");

  await expect(page.getByText("1 order")).toBeVisible();
  await expect(page.getByRole("list", { name: /^Orders$/ }).getByRole("listitem")).toHaveText([
    "#1010 — Margaret — shipped",
  ]);
  await expect(page).toHaveURL("/?status=shipped&q=101");
});

test("loads filtered orders from the URL and keeps them after reload", async ({ page }) => {
  await page.goto("/?status=refunded&q=20");

  await expect(page.getByText("1 order")).toBeVisible();
  await expect(page.getByLabel("Status")).toHaveValue("refunded");
  await expect(page.getByRole("textbox", { name: /^Search$/ })).toHaveValue("20");
  await expect(page.getByRole("list", { name: /^Orders$/ }).getByRole("listitem")).toHaveText([
    "#2010 — Radia — refunded",
  ]);

  await page.reload();

  await expect(page.getByText("1 order")).toBeVisible();
  await expect(page.getByLabel("Status")).toHaveValue("refunded");
  await expect(page.getByRole("textbox", { name: /^Search$/ })).toHaveValue("20");
  await expect(page.getByRole("list", { name: /^Orders$/ }).getByRole("listitem")).toHaveText([
    "#2010 — Radia — refunded",
  ]);
  await expect(page).toHaveURL("/?status=refunded&q=20");
});

test("clears filters and shows every order", async ({ page }) => {
  await page.goto("/?status=shipped&q=101");

  await page.getByRole("button", { name: /^Clear filters$/ }).click();

  await expect(page.getByText("8 orders")).toBeVisible();
  await expect(page.getByLabel("Status")).toHaveValue("");
  await expect(page.getByRole("textbox", { name: /^Search$/ })).toHaveValue("");
  await expect(page.getByRole("list", { name: /^Orders$/ }).getByRole("listitem")).toHaveText(allOrders);
  await expect(page).toHaveURL("/");
});

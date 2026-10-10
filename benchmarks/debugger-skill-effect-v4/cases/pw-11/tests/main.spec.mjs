
import { test, expect } from "@playwright/test";
import { openMenu } from "./helpers.mjs";

test("the menu lists reports", async ({ page }) => {
  await page.goto("/");
  await openMenu(page);
  await expect(page.locator("#reports")).toBeVisible();
});

test("the menu lists settings", async ({ page }) => {
  await page.goto("/");
  await openMenu(page);
  await expect(page.locator("#settings")).toBeVisible();
});

test("the summary shows the total with tax", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#summary")).toHaveText("Total: 42");
});

test("the page is titled Dashboard", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Dashboard");
});

test("the summary is rendered", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#summary")).toContainText("Total:");
});

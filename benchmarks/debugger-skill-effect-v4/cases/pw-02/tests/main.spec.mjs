
import { test, expect } from "@playwright/test";

test("shows the page title", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#title")).toHaveText("Your orders");
});

test("lists the three most recent orders", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#orders li")).toHaveCount(3);
});

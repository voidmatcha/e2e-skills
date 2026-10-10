
import { test, expect } from "@playwright/test";

test("greets the signed-in user", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#greeting")).toHaveText("Welcome, Sam");
});

test("sets the page title", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Home");
});


import { test, expect } from "@playwright/test";

test("greets the profile owner by name", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#hello")).toHaveText("Hello, Ada");
});

test("saving shows the confirmation", async ({ page }) => {
  await page.goto("/");
  await page.click("#save-btn");
  await expect(page.locator("#saved")).toBeVisible();
});

test("the page is titled", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Profile");
});

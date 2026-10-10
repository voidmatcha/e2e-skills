
import { test, expect } from "@playwright/test";

test("a free account sees the free plan", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#plan")).toHaveText("free");
});

test("a pro account sees the pro plan", async ({ page }) => {
  await page.goto("/");
  await page.route("**/api/config", (route) => route.fulfill({ json: { plan: "pro" } }));
  await expect(page.locator("#plan")).toHaveText("pro");
});

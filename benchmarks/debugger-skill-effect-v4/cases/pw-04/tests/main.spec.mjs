
import { test, expect } from "@playwright/test";

test("shows the report heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1")).toHaveText("Quarterly report");
});

test("shows the quarterly total", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#total")).toHaveText("42", { timeout: 600 });
});

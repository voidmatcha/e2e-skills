
import { test, expect } from "@playwright/test";

test("the counter starts at zero", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#n")).toHaveText("0");
});

test("increment raises the counter to one", async ({ page }) => {
  await page.goto("/");
  await page.click("#inc");
  await expect(page.locator("#n")).toHaveText("1");
});


import { test, expect } from "@playwright/test";

test("adding a book puts one item in the cart", async ({ page }) => {
  await page.goto("/");
  await page.click("#add");
  await expect(page.locator("#count")).toHaveText("1");
});

test("a new visitor starts with an empty cart", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#count")).toHaveText("0");
});

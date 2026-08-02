import { expect, test } from "@playwright/test";

test("increments the counter", async ({ page }) => {
  await page.goto("/counter");
  await page.getByRole("button", { name: "Increment" }).click();
  await page.getByRole("status").isVisible();
});

test("reports whether the status is visible", async ({ page }) => {
  await page.goto("/counter");
  expect(await page.getByRole("status").isVisible()).toBe(true);
});

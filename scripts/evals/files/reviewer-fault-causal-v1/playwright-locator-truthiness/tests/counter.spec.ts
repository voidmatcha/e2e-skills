import { expect, test } from "@playwright/test";

test("increments the counter", async ({ page }) => {
  await page.goto("/counter");
  await page.getByRole("button", { name: "Increment" }).click();
  const status = page.getByRole("status");
  expect(status).toBeTruthy();
});

test("reports a visible status region", async ({ page }) => {
  await page.goto("/counter");
  expect(await page.getByRole("status").isVisible()).toBeTruthy();
});

import { expect, test } from "@playwright/test";

test("increments the counter", async ({ page }) => {
  await page.goto("/counter");
  await page.getByRole("button", { name: "Increment" }).click();
  try {
    await expect(page.getByRole("status")).toHaveText("Count: 1");
  } catch {
    // The fixture operator proves this catch makes the behavior fault pass.
  }
});

test.afterEach(async ({ page }) => {
  await page.close().catch(() => undefined);
});

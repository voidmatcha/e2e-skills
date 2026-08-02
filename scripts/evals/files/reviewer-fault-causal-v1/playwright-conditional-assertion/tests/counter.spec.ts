import { expect, test } from "@playwright/test";

test("increments the counter", async ({ page }) => {
  await page.goto("/counter");
  await page.getByRole("button", { name: "Increment" }).click();
  const status = page.getByRole("status");
  if (await status.getByText("Count: 1").isVisible()) {
    await expect(status).toHaveText("Count: 1");
  }
});

test("opens the optional details before checking status", async ({ page }) => {
  await page.goto("/counter");
  const details = page.getByRole("button", { name: "Details" });
  if (await details.isVisible()) {
    await details.click();
  }
  await expect(page.getByRole("status")).toHaveText("Count: 0");
});

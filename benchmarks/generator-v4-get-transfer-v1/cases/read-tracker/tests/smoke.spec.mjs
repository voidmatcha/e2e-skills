import { expect, test } from "@playwright/test";

test("shows the reading tracker", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Reading tracker" })).toBeVisible();
});

import { expect, test } from "@playwright/test";

test("shows the color poll", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Color poll" })).toBeVisible();
});

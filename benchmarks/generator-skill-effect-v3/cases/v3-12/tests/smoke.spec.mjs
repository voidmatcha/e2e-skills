import { expect, test } from "@playwright/test";

test("shows the garden heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Garden planner" })).toBeVisible();
});

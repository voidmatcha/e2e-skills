import { expect, test } from "@playwright/test";

test("shows the board heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sprint board" })).toBeVisible();
});

import { expect, test } from "@playwright/test";

test("shows the tags heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Article tags" })).toBeVisible();
});

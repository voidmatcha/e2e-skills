import { expect, test } from "@playwright/test";

test("shows the quiz heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Quick quiz" })).toBeVisible();
});

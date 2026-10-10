import { expect, test } from "@playwright/test";

test("shows the issues heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Issues" })).toBeVisible();
});

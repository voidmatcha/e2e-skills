import { expect, test } from "@playwright/test";

test("shows the verification email links", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Verify email" })).toBeVisible();
});

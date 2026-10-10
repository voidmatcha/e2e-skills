import { expect, test } from "@playwright/test";

test("shows the records heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Records" })).toBeVisible();
});

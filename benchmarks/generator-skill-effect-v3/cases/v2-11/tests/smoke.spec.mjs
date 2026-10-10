import { expect, test } from "@playwright/test";

test("shows the files heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Files" })).toBeVisible();
});

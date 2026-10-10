import { expect, test } from "@playwright/test";

test("shows the editor heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Editor" })).toBeVisible();
});

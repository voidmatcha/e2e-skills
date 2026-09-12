import { expect, test } from "@playwright/test";

test("opens the staff hold queue", async ({ page }) => {
  await page.goto("/staff/holds");
  await expect(page.getByRole("heading", { name: "Hold queue" })).toBeVisible();
});

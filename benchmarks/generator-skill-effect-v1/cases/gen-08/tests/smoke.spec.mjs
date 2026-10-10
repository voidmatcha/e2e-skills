import { expect, test } from "@playwright/test";

test("shows the poll question", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Which editor do you use?" })).toBeVisible();
});

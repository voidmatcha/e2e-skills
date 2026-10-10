import { expect, test } from "@playwright/test";

test("shows the task board heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Task board" })).toBeVisible();
});

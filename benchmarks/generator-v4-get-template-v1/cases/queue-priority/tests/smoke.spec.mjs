import { expect, test } from "@playwright/test";

test("shows the priority queue", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Queue priority" })).toBeVisible();
});

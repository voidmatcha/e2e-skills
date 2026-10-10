import { expect, test } from "@playwright/test";

test("shows the inbox heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Inbox/ })).toBeVisible();
});

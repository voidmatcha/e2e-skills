import { expect, test } from "@playwright/test";

test("shows the guestbook heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Guestbook" })).toBeVisible();
});

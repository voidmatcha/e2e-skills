import { expect, test } from "@playwright/test";

test("shows the envelopes heading", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Budget envelopes" })).toBeVisible();
});

import { expect, test } from "@playwright/test";

test("opens the ready hold for card 418", async ({ page }) => {
  await page.goto("/staff/holds/ready");
  const readyRow = page.getByRole("row", { name: "Ready for pickup" });
  await readyRow.getByRole("link", { name: "Card 418", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Hold details", exact: true })).toBeVisible();
});

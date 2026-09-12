import { expect, test } from "@playwright/test";

let selectedBranch = "east";

test("staff can switch the queue to the west branch", async ({ page }) => {
  selectedBranch = "west";
  await page.goto(`/staff/holds?branch=${selectedBranch}`);
  await expect(page.getByTestId("branch-name")).toHaveText("West Branch");
});

test("east branch queue shows its pickup notice", async ({ page }) => {
  await page.goto(`/staff/holds?branch=${selectedBranch}`);
  await expect(page.getByTestId("east-pickup-notice")).toBeVisible();
});

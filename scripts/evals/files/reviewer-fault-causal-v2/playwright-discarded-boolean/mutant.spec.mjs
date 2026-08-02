import { expect, test } from "@playwright/test";

test("verifies the incremented status content", async ({ page }) => {
  const query =
    process.env.FIXTURE_FAULT_MODE === "behavior" ? "?behavior-fault" : "";
  await page.goto(`/${query}`);

  const status = page.getByRole("status");
  await expect(status).toHaveText("Count: 0");
  await page.getByRole("button", { name: "Increment" }).click();
  await status.isVisible();
});

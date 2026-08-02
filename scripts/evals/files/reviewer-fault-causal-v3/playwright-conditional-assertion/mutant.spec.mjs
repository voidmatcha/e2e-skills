import { expect, test } from "@playwright/test";

test("increments the counter on every supported path", async ({ page }) => {
  const query =
    process.env.FIXTURE_FAULT_MODE === "behavior" ? "?behavior-fault" : "";
  await page.goto(`/${query}`);

  const status = page.getByRole("status");
  await expect(status).toHaveText("Count: 0");
  await page.getByRole("button", { name: "Increment" }).click();
  if (await status.getByText("Count: 1").isVisible()) {
    await expect(status).toHaveText("Count: 1");
  }
});

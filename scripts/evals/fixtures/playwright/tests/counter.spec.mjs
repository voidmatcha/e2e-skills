import { expect, test } from "@playwright/test";

test("increments the counter", async ({ page }) => {
  const query =
    process.env.FIXTURE_FAULT_MODE === "behavior" ? "?behavior-fault" : "";
  await page.goto(`/${query}`);

  const status = page.getByRole("status");
  const button = page.getByRole("button", { name: "Increment" });
  await expect(status).toHaveText("Count: 0");
  await button.click();
  await expect(status).toHaveText("Count: 1");
});

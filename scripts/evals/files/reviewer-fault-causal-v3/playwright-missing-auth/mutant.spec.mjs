import { expect, test } from "@playwright/test";

test("opens the authenticated account surface", async ({ page }) => {
  const query =
    process.env.FIXTURE_FAULT_MODE === "auth"
      ? "?account-view&auth-fault"
      : "?account-view";
  await page.goto(`/${query}`);
  await expect(
    page.getByRole("heading", { name: "Account" }),
  ).toBeVisible();
});

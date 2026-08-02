import { expect, test } from "@playwright/test";

test("opens the authenticated account surface", async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem("fixture-auth", "valid"),
  );
  const query =
    process.env.FIXTURE_FAULT_MODE === "auth"
      ? "?account-view&auth-fault"
      : "?account-view";
  await page.goto(`/${query}`);
  await expect(page.getByTestId("account-name")).toHaveText("Ada Lovelace");
});

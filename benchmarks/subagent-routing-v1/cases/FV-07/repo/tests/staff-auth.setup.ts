import { test as setup } from "@playwright/test";

setup("authenticate branch staff", async ({ page }) => {
  await page.goto("/staff/sign-in");
  await page.getByLabel("Staff ID").fill(process.env.STAFF_TEST_ID ?? "fixture-librarian");
  await page.getByLabel("Access token").fill(process.env.STAFF_TEST_TOKEN ?? "fixture-token");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.context().storageState({ path: "staff-state.json" });
});

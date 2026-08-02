import { expect, test } from "@playwright/test";

test("#15 floating assertion promise", async ({ page }) => {
  const query =
    process.env.FIXTURE_FAULT_MODE === "behavior" ? "?behavior-fault" : "";
  await page.goto(`/${query}`);
  await page.getByRole("button", { name: "Increment" }).click();

  const status = page.getByRole("status");
  await expect(status).toHaveText("Count: 1", { timeout: 1000 });
});

test("#16 floating locator action promise", async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem("fixture-auth", "valid"),
  );
  const query =
    process.env.FIXTURE_FAULT_MODE === "auth"
      ? "?account-view&auth-fault"
      : "?account-view";
  await page.goto(`/${query}`);

  await page.getByTestId("account-name").click({ timeout: 1000 });
});

import { expect, test } from "@playwright/test";

test("proves the increment request fired", async ({ page }) => {
  const query =
    process.env.FIXTURE_FAULT_MODE === "write" ? "?write-fault" : "";
  await page.goto(`/${query}`);

  // Mutant trusts optimistic UI and removes request proof.
  await page.getByRole("button", { name: "Increment" }).click();
  await expect(page.getByRole("status")).toHaveText("Count: 1");
});

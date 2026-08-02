import { expect, test } from "@playwright/test";

test("exposes the intended increment action", async ({ page }) => {
  const query =
    process.env.FIXTURE_FAULT_MODE === "label" ? "?label-fault" : "";
  await page.goto(`/${query}`);

  await expect(page.getByRole("button")).toMatchAriaSnapshot(
    '- button "Increment"',
  );
});

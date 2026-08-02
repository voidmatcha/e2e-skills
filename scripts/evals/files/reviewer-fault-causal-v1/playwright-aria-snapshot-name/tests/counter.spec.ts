import { expect, test } from "@playwright/test";

test("exposes the intended increment action", async ({ page }) => {
  await page.goto("/counter");
  await expect(page.getByRole("button")).toMatchAriaSnapshot("- button");
});

test("exposes the intended reset action", async ({ page }) => {
  await page.goto("/counter");
  await expect(page.getByRole("button", { name: "Reset" })).toMatchAriaSnapshot(
    '- button "Reset"',
  );
});

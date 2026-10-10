import { expect, test } from "@playwright/test";

const recordNames = (from, to) =>
  Array.from({ length: to - from + 1 }, (_, i) => "Record " + (from + i));

test.describe("paginated records", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // The list is rendered client-side; wait for the first page before interacting.
    await expect(page.getByText("Page 1 of 3")).toBeVisible();
  });

  test("next shows the following ten records and updates the indicator", async ({ page }) => {
    await page.getByRole("button", { name: "Next" }).click();

    await expect(page.getByText("Page 2 of 3")).toBeVisible();
    await expect(page.getByRole("list", { name: "Records" }).getByRole("listitem")).toHaveText(
      recordNames(11, 20),
    );
  });

  test("first page lists Record 1 to Record 10", async ({ page }) => {
    await expect(page.getByRole("list", { name: "Records" }).getByRole("listitem")).toHaveText(
      recordNames(1, 10),
    );
  });

  test("last page lists exactly Record 21, Record 22 and Record 23", async ({ page }) => {
    const next = page.getByRole("button", { name: "Next" });
    await next.click();
    await expect(page.getByText("Page 2 of 3")).toBeVisible();
    await next.click();

    await expect(page.getByText("Page 3 of 3")).toBeVisible();
    await expect(page.getByRole("list", { name: "Records" }).getByRole("listitem")).toHaveText(
      recordNames(21, 23),
    );
  });

  test("previous is disabled on the first page", async ({ page }) => {
    await expect(page.getByRole("button", { name: "Previous" })).toBeDisabled();
  });

  test("next is disabled on the last page", async ({ page }) => {
    const next = page.getByRole("button", { name: "Next" });
    await next.click();
    await expect(page.getByText("Page 2 of 3")).toBeVisible();
    await next.click();
    await expect(page.getByText("Page 3 of 3")).toBeVisible();

    await expect(next).toBeDisabled();
  });

  test("previous returns to the preceding page", async ({ page }) => {
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Page 2 of 3")).toBeVisible();

    await page.getByRole("button", { name: "Previous" }).click();

    await expect(page.getByText("Page 1 of 3")).toBeVisible();
    await expect(page.getByRole("list", { name: "Records" }).getByRole("listitem")).toHaveText(
      recordNames(1, 10),
    );
  });
});

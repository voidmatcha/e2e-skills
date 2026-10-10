import { expect, test } from "@playwright/test";

const names = (from, to) =>
  Array.from({ length: to - from + 1 }, (_, i) => "Record " + (from + i));

test.describe("paginated records", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("first page lists Record 1 to Record 10 and reads Page 1 of 3", async ({ page }) => {
    await expect(page.getByRole("listitem")).toHaveText(names(1, 10));
    await expect(page.getByRole("navigation", { name: "Pagination" })).toContainText("Page 1 of 3");
  });

  test("Next shows the following ten records and updates the indicator", async ({ page }) => {
    await page.getByRole("button", { name: "Next" }).click();

    await expect(page.getByRole("listitem")).toHaveText(names(11, 20));
    await expect(page.getByRole("navigation", { name: "Pagination" })).toContainText("Page 2 of 3");
  });

  test("last page lists exactly Record 21, Record 22 and Record 23", async ({ page }) => {
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Next" }).click();

    await expect(page.getByRole("listitem")).toHaveText(names(21, 23));
    await expect(page.getByRole("navigation", { name: "Pagination" })).toContainText("Page 3 of 3");
  });

  test("Previous is disabled on the first page", async ({ page }) => {
    await expect(page.getByRole("navigation", { name: "Pagination" })).toContainText("Page 1 of 3");
    await expect(page.getByRole("button", { name: "Previous" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  test("Next is disabled on the last page", async ({ page }) => {
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Next" }).click();

    await expect(page.getByRole("navigation", { name: "Pagination" })).toContainText("Page 3 of 3");
    await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Previous" })).toBeEnabled();
  });

  test("Previous returns to the preceding page", async ({ page }) => {
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByRole("listitem")).toHaveText(names(11, 20));

    await page.getByRole("button", { name: "Previous" }).click();

    await expect(page.getByRole("listitem")).toHaveText(names(1, 10));
    await expect(page.getByRole("navigation", { name: "Pagination" })).toContainText("Page 1 of 3");
  });
});

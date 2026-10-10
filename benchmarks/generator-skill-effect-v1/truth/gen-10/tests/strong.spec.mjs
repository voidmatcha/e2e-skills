import { expect, test } from "@playwright/test";

const rows = (page) => page.getByRole("list", { name: "Records" }).getByRole("listitem");
const next = (page) => page.getByRole("button", { name: "Next" });
const previous = (page) => page.getByRole("button", { name: "Previous" });
const names = (from, to) => Array.from({ length: to - from + 1 }, (_, i) => `Record ${from + i}`);

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("first page lists records 1 to 10", async ({ page }) => {
  await expect(rows(page)).toHaveText(names(1, 10));
  await expect(page.getByText("Page 1 of 3")).toBeVisible();
  await expect(previous(page)).toBeDisabled();
  await expect(next(page)).toBeEnabled();
});

test("next advances and updates the indicator", async ({ page }) => {
  await next(page).click();
  await expect(rows(page)).toHaveText(names(11, 20));
  await expect(page.getByText("Page 2 of 3")).toBeVisible();
  await expect(previous(page)).toBeEnabled();
});

test("last page lists exactly records 21 to 23", async ({ page }) => {
  await next(page).click();
  await next(page).click();
  await expect(rows(page)).toHaveText(names(21, 23));
  await expect(page.getByText("Page 3 of 3")).toBeVisible();
  await expect(next(page)).toBeDisabled();
});

test("previous returns to the preceding page", async ({ page }) => {
  await next(page).click();
  await expect(page.getByText("Page 2 of 3")).toBeVisible();
  await previous(page).click();
  await expect(rows(page)).toHaveText(names(1, 10));
  await expect(page.getByText("Page 1 of 3")).toBeVisible();
  await expect(previous(page)).toBeDisabled();
});

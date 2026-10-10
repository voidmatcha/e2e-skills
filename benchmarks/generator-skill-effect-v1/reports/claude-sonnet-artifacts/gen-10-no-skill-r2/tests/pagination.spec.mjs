import { expect, test } from "@playwright/test";

const names = (from, to) => Array.from({ length: to - from + 1 }, (_, i) => "Record " + (from + i));

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#pg-status")).toHaveText("Page 1 of 3");
});

const records = (page) => page.getByRole("list", { name: "Records" }).getByRole("listitem");
const prev = (page) => page.getByRole("button", { name: "Previous" });
const next = (page) => page.getByRole("button", { name: "Next" });

test("first page lists Record 1 to Record 10", async ({ page }) => {
  await expect(records(page)).toHaveText(names(1, 10));
  await expect(page.getByText("Page 1 of 3")).toBeVisible();
});

test("Next shows the following ten records", async ({ page }) => {
  await next(page).click();
  await expect(page.getByText("Page 2 of 3")).toBeVisible();
  await expect(records(page)).toHaveText(names(11, 20));
});

test("last page lists exactly Record 21 to Record 23", async ({ page }) => {
  await next(page).click();
  await next(page).click();
  await expect(page.getByText("Page 3 of 3")).toBeVisible();
  await expect(records(page)).toHaveText(names(21, 23));
});

test("Previous is disabled on the first page, Next on the last", async ({ page }) => {
  await expect(prev(page)).toBeDisabled();
  await expect(next(page)).toBeEnabled();
  await next(page).click();
  await next(page).click();
  await expect(page.getByText("Page 3 of 3")).toBeVisible();
  await expect(next(page)).toBeDisabled();
  await expect(prev(page)).toBeEnabled();
});

test("Previous returns to the preceding page", async ({ page }) => {
  await next(page).click();
  await expect(records(page)).toHaveText(names(11, 20));
  await prev(page).click();
  await expect(page.getByText("Page 1 of 3")).toBeVisible();
  await expect(records(page)).toHaveText(names(1, 10));
});

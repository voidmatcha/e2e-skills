import { expect, test } from "@playwright/test";

const names = (from, to) =>
  Array.from({ length: to - from + 1 }, (_, i) => "Record " + (from + i));

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("first page lists Record 1 to Record 10 with Page 1 of 3", async ({ page }) => {
  const records = page.getByRole("list", { name: "Records" }).getByRole("listitem");
  await expect(records).toHaveText(names(1, 10));
  await expect(page.getByRole("navigation", { name: "Pagination" })).toContainText("Page 1 of 3");
});

test("Next shows the following ten records and updates the indicator", async ({ page }) => {
  await page.getByRole("button", { name: "Next" }).click();

  const records = page.getByRole("list", { name: "Records" }).getByRole("listitem");
  await expect(records).toHaveText(names(11, 20));
  await expect(page.getByRole("navigation", { name: "Pagination" })).toContainText("Page 2 of 3");
});

test("last page lists exactly Record 21 to Record 23", async ({ page }) => {
  const next = page.getByRole("button", { name: "Next" });
  await next.click();
  await expect(page.getByRole("navigation", { name: "Pagination" })).toContainText("Page 2 of 3");
  await next.click();

  const records = page.getByRole("list", { name: "Records" }).getByRole("listitem");
  await expect(records).toHaveText(names(21, 23));
  await expect(page.getByRole("navigation", { name: "Pagination" })).toContainText("Page 3 of 3");
});

test("Previous is disabled on the first page and Next on the last page", async ({ page }) => {
  const previous = page.getByRole("button", { name: "Previous" });
  const next = page.getByRole("button", { name: "Next" });
  const nav = page.getByRole("navigation", { name: "Pagination" });

  await expect(nav).toContainText("Page 1 of 3");
  await expect(previous).toBeDisabled();
  await expect(next).toBeEnabled();

  await next.click();
  await expect(nav).toContainText("Page 2 of 3");
  await expect(previous).toBeEnabled();
  await expect(next).toBeEnabled();

  await next.click();
  await expect(nav).toContainText("Page 3 of 3");
  await expect(next).toBeDisabled();
  await expect(previous).toBeEnabled();
});

test("Previous returns to the preceding page", async ({ page }) => {
  const nav = page.getByRole("navigation", { name: "Pagination" });
  const records = page.getByRole("list", { name: "Records" }).getByRole("listitem");

  await page.getByRole("button", { name: "Next" }).click();
  await expect(nav).toContainText("Page 2 of 3");

  await page.getByRole("button", { name: "Previous" }).click();
  await expect(nav).toContainText("Page 1 of 3");
  await expect(records).toHaveText(names(1, 10));
});

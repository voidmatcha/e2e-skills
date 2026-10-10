import { expect, test } from "@playwright/test";

const items = (page) => page.getByRole("list", { name: "Products" }).getByRole("listitem");
const search = (page) => page.getByLabel("Search products");

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("narrows the list to matching names", async ({ page }) => {
  await expect(items(page)).toHaveCount(6);
  await search(page).fill("Jacket");
  await expect(items(page)).toHaveText([/Alpine Jacket/]);
});

test("ignores letter case", async ({ page }) => {
  await search(page).fill("camp mug");
  await expect(items(page)).toHaveText([/Camp Mug/]);
});

test("shows the result count", async ({ page }) => {
  await expect(page.getByText("Showing 6 of 6 products")).toBeVisible();
  await search(page).fill("e");
  await expect(page.getByText("Showing 5 of 6 products")).toBeVisible();
});

test("shows the empty state when nothing matches", async ({ page }) => {
  await search(page).fill("zzz");
  await expect(items(page)).toHaveCount(0);
  await expect(page.getByText("No products match")).toBeVisible();
  await expect(page.getByText("Showing 0 of 6 products")).toBeVisible();
});

test("clear resets the box and the list", async ({ page }) => {
  await search(page).fill("Tote");
  await expect(items(page)).toHaveCount(1);
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(search(page)).toHaveValue("");
  await expect(items(page)).toHaveCount(6);
});

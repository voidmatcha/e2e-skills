import { expect, test } from "@playwright/test";

const ALL_PRODUCTS = [
  "Alpine Jacket",
  "Trail Runner Shoes",
  "Canvas Tote",
  "Merino Beanie",
  "Rain Shell",
  "Camp Mug",
];

// Each list item reads "<name> — $<price>", so match on the name prefix.
const names = (list) => list.map((name) => new RegExp(`^${name}\\b`));

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("shows all six products before any search", async ({ page }) => {
  await expect(page.getByRole("list", { name: "Products" }).getByRole("listitem")).toHaveText(names(ALL_PRODUCTS));
  await expect(page.getByText("Showing 6 of 6 products")).toBeVisible();
  await expect(page.getByText("No products match")).toBeHidden();
});

test("typing narrows the list to products whose name contains the text", async ({ page }) => {
  await page.getByLabel("Search products").fill("an");

  await expect(page.getByRole("list", { name: "Products" }).getByRole("listitem")).toHaveText(
    names(["Canvas Tote", "Merino Beanie"]),
  );
  await expect(page.getByText("Showing 2 of 6 products")).toBeVisible();
});

test("typing key by key narrows the list on each input", async ({ page }) => {
  await page.getByLabel("Search products").pressSequentially("ra");
  await expect(page.getByText("Showing 2 of 6 products")).toBeVisible();

  await page.getByLabel("Search products").pressSequentially("in");
  await expect(page.getByRole("list", { name: "Products" }).getByRole("listitem")).toHaveText(names(["Rain Shell"]));
  await expect(page.getByText("Showing 1 of 6 products")).toBeVisible();
});

test("matching ignores letter case", async ({ page }) => {
  const search = page.getByLabel("Search products");
  const items = page.getByRole("list", { name: "Products" }).getByRole("listitem");

  await search.fill("ALPINE");
  await expect(items).toHaveText(names(["Alpine Jacket"]));
  await expect(page.getByText("Showing 1 of 6 products")).toBeVisible();

  await search.fill("camp mug");
  await expect(items).toHaveText(names(["Camp Mug"]));
  await expect(page.getByText("Showing 1 of 6 products")).toBeVisible();
});

test("shows an empty list and a message when nothing matches", async ({ page }) => {
  await page.getByLabel("Search products").fill("zzz");

  await expect(page.getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("No products match")).toBeVisible();
  await expect(page.getByText("Showing 0 of 6 products")).toBeVisible();
});

test("Clear empties the search box and shows all products again", async ({ page }) => {
  const search = page.getByLabel("Search products");
  await search.fill("zzz");
  await expect(page.getByText("No products match")).toBeVisible();

  await page.getByRole("button", { name: "Clear" }).click();

  await expect(search).toHaveValue("");
  await expect(page.getByRole("list", { name: "Products" }).getByRole("listitem")).toHaveText(names(ALL_PRODUCTS));
  await expect(page.getByText("Showing 6 of 6 products")).toBeVisible();
  await expect(page.getByText("No products match")).toBeHidden();
});

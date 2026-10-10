import { expect, test } from "@playwright/test";

const ALL = [
  "Alpine Jacket",
  "Trail Runner Shoes",
  "Canvas Tote",
  "Merino Beanie",
  "Rain Shell",
  "Camp Mug",
];

const names = (page) => page.locator("#ps-list li.product");

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("shows all six products initially", async ({ page }) => {
  await expect(names(page)).toHaveCount(6);
  for (const [i, name] of ALL.entries()) {
    await expect(names(page).nth(i)).toContainText(name);
  }
  await expect(page.locator("#ps-count")).toHaveText("Showing 6 of 6 products");
});

test("typing narrows the list to names containing the text", async ({ page }) => {
  await page.getByLabel("Search products").fill("ra");
  await expect(names(page)).toHaveCount(2);
  await expect(names(page).nth(0)).toContainText("Trail Runner Shoes");
  await expect(names(page).nth(1)).toContainText("Rain Shell");
  await expect(page.locator("#ps-count")).toHaveText("Showing 2 of 6 products");
  await expect(page.locator("#ps-empty")).toBeHidden();
});

test("narrows incrementally while typing", async ({ page }) => {
  const box = page.getByLabel("Search products");
  await box.pressSequentially("ca");
  await expect(names(page)).toHaveCount(2); // Canvas Tote, Camp Mug
  await expect(page.locator("#ps-count")).toHaveText("Showing 2 of 6 products");
  await box.pressSequentially("m");
  await expect(names(page)).toHaveCount(1);
  await expect(names(page).first()).toContainText("Camp Mug");
  await expect(page.locator("#ps-count")).toHaveText("Showing 1 of 6 products");
});

test("matching ignores letter case", async ({ page }) => {
  const box = page.getByLabel("Search products");
  await box.fill("MERINO");
  await expect(names(page)).toHaveCount(1);
  await expect(names(page).first()).toContainText("Merino Beanie");
  await box.fill("rAiN sHeLl");
  await expect(names(page)).toHaveCount(1);
  await expect(names(page).first()).toContainText("Rain Shell");
  await expect(page.locator("#ps-count")).toHaveText("Showing 1 of 6 products");
});

test("shows a message and an empty list when nothing matches", async ({ page }) => {
  await page.getByLabel("Search products").fill("zzz");
  await expect(names(page)).toHaveCount(0);
  await expect(page.getByText("No products match")).toBeVisible();
  await expect(page.locator("#ps-count")).toHaveText("Showing 0 of 6 products");
});

test("Clear empties the search box and restores all products", async ({ page }) => {
  const box = page.getByLabel("Search products");
  await box.fill("zzz");
  await expect(page.getByText("No products match")).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(box).toHaveValue("");
  await expect(names(page)).toHaveCount(6);
  await expect(page.locator("#ps-count")).toHaveText("Showing 6 of 6 products");
  await expect(page.locator("#ps-empty")).toBeHidden();
});

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
const search = (page) => page.getByLabel("Search products");
const status = (page) => page.locator("#ps-count");

async function expectNames(page, expected) {
  await expect(names(page)).toHaveCount(expected.length);
  for (const [i, name] of expected.entries()) {
    await expect(names(page).nth(i)).toContainText(name);
  }
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("initially shows all six products", async ({ page }) => {
  await expectNames(page, ALL);
  await expect(status(page)).toHaveText("Showing 6 of 6 products");
  await expect(page.getByText("No products match")).toBeHidden();
});

test("typing narrows the list to names containing the text", async ({ page }) => {
  await search(page).pressSequentially("ra");
  await expectNames(page, ["Trail Runner Shoes", "Rain Shell"]);
  await expect(status(page)).toHaveText("Showing 2 of 6 products");
});

test("matching ignores letter case", async ({ page }) => {
  await search(page).fill("MERINO");
  await expectNames(page, ["Merino Beanie"]);
  await expect(status(page)).toHaveText("Showing 1 of 6 products");

  await search(page).fill("camp mug");
  await expectNames(page, ["Camp Mug"]);
});

test("shows a message and an empty list when nothing matches", async ({ page }) => {
  await search(page).fill("zzz");
  await expect(names(page)).toHaveCount(0);
  await expect(page.getByText("No products match")).toBeVisible();
  await expect(status(page)).toHaveText("Showing 0 of 6 products");
});

test("Clear empties the search box and restores all products", async ({ page }) => {
  await search(page).fill("zzz");
  await expect(page.getByText("No products match")).toBeVisible();

  await page.getByRole("button", { name: "Clear" }).click();
  await expect(search(page)).toHaveValue("");
  await expectNames(page, ALL);
  await expect(status(page)).toHaveText("Showing 6 of 6 products");
  await expect(page.getByText("No products match")).toBeHidden();
});

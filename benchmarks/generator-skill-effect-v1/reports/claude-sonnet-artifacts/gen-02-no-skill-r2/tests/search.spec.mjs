import { expect, test } from "@playwright/test";

const ALL = [
  "Alpine Jacket",
  "Trail Runner Shoes",
  "Canvas Tote",
  "Merino Beanie",
  "Rain Shell",
  "Camp Mug",
];

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

const items = (page) => page.getByRole("list", { name: "Products" }).getByRole("listitem");
const search = (page) => page.getByLabel("Search products");

async function expectNames(page, names) {
  await expect(items(page)).toHaveCount(names.length);
  for (const [i, name] of names.entries()) {
    await expect(items(page).nth(i)).toContainText(name);
  }
  await expect(page.getByText(`Showing ${names.length} of 6 products`)).toBeVisible();
}

test("shows all six products initially", async ({ page }) => {
  await expectNames(page, ALL);
  await expect(page.getByText("No products match")).toBeHidden();
});

test("typing narrows the list to names containing the text", async ({ page }) => {
  await search(page).pressSequentially("ra");
  await expectNames(page, ["Trail Runner Shoes", "Rain Shell"]);
  await search(page).pressSequentially("i");
  await expectNames(page, ["Trail Runner Shoes", "Rain Shell"].filter((n) => n.toLowerCase().includes("rai")));
});

test("matches a substring in the middle of a name", async ({ page }) => {
  await search(page).fill("mug");
  await expectNames(page, ["Camp Mug"]);
});

test("matching ignores letter case", async ({ page }) => {
  await search(page).fill("aLPINE jACKET");
  await expectNames(page, ["Alpine Jacket"]);
  await search(page).fill("TOTE");
  await expectNames(page, ["Canvas Tote"]);
});

test("status line reflects the current list", async ({ page }) => {
  await search(page).fill("e");
  // Alpine Jacket, Trail Runner Shoes, Canvas Tote, Merino Beanie, Rain Shell
  await expect(page.locator("#ps-count")).toHaveText("Showing 5 of 6 products");
});

test("shows an empty list and message when nothing matches", async ({ page }) => {
  await search(page).fill("zzz");
  await expect(items(page)).toHaveCount(0);
  await expect(page.getByText("No products match")).toBeVisible();
  await expect(page.getByText("Showing 0 of 6 products")).toBeVisible();
});

test("Clear empties the search box and restores all products", async ({ page }) => {
  await search(page).fill("zzz");
  await expect(page.getByText("No products match")).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(search(page)).toHaveValue("");
  await expectNames(page, ALL);
  await expect(page.getByText("No products match")).toBeHidden();
});

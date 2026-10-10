import { expect, test } from "@playwright/test";

const names = [
  "Alpine Jacket",
  "Trail Runner Shoes",
  "Canvas Tote",
  "Merino Beanie",
  "Rain Shell",
  "Camp Mug",
];

// Each list item reads "<name> — $<price>", so match on the name prefix.
const startingWith = (list) => list.map((name) => new RegExp(`^${name} — \\$\\d+$`));

test.describe("product search", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("shows all six products on load", async ({ page }) => {
    await expect(page.getByRole("list", { name: "Products" }).getByRole("listitem")).toHaveText(startingWith(names));
    await expect(page.getByText("Showing 6 of 6 products")).toBeVisible();
  });

  test("typing narrows the list to products whose name contains the text", async ({ page }) => {
    await page.getByLabel("Search products").pressSequentially("ra");

    await expect(page.getByRole("list", { name: "Products" }).getByRole("listitem")).toHaveText(
      startingWith(["Trail Runner Shoes", "Rain Shell"]),
    );
    await expect(page.getByText("Showing 2 of 6 products")).toBeVisible();
    await expect(page.getByText("No products match")).toBeHidden();
  });

  test("matching ignores letter case", async ({ page }) => {
    await page.getByLabel("Search products").fill("cAMP mUG");

    await expect(page.getByRole("list", { name: "Products" }).getByRole("listitem")).toHaveText(
      startingWith(["Camp Mug"]),
    );
    await expect(page.getByText("Showing 1 of 6 products")).toBeVisible();
  });

  test("shows an empty list and a message when nothing matches", async ({ page }) => {
    await page.getByLabel("Search products").fill("zzz");

    await expect(page.getByText("No products match")).toBeVisible();
    await expect(page.getByRole("list", { name: "Products" }).getByRole("listitem")).toHaveCount(0);
    await expect(page.getByText("Showing 0 of 6 products")).toBeVisible();
  });

  test("Clear empties the search box and shows all six products again", async ({ page }) => {
    const searchBox = page.getByLabel("Search products");
    await searchBox.fill("zzz");
    await expect(page.getByText("No products match")).toBeVisible();

    await page.getByRole("button", { name: "Clear" }).click();

    await expect(page.getByRole("list", { name: "Products" }).getByRole("listitem")).toHaveText(startingWith(names));
    await expect(searchBox).toHaveValue("");
    await expect(page.getByText("Showing 6 of 6 products")).toBeVisible();
    await expect(page.getByText("No products match")).toBeHidden();
  });
});

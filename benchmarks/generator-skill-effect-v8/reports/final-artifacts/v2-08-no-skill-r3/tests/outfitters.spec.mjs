import { expect, test } from "@playwright/test";

const products = [
  { name: "Field Notebook", price: "$9.50" },
  { name: "Brass Compass", price: "$42.00" },
  { name: "Wool Blanket", price: "$68.00" },
];

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("links from the product list to each product page", async ({ page }) => {
  await page.goto("/");

  for (const product of products) {
    await page.getByRole("link", { name: product.name }).click();
    await expect(page.getByRole("heading", { name: product.name })).toBeVisible();
    await expect(page.locator("#sf-product-price")).toHaveText(product.price);
    await page.getByRole("link", { name: "Back to products" }).click();
  }
});

test("saves a product to the wishlist across pages and reloads", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Wishlist (0)" })).toBeVisible();

  await page.getByRole("link", { name: "Brass Compass" }).click();
  await expect(page.getByRole("heading", { name: "Brass Compass" })).toBeVisible();

  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  await expect(page.getByRole("link", { name: "Wishlist (1)" })).toBeVisible();

  await page.getByRole("link", { name: "Back to products" }).click();
  await expect(page.getByRole("link", { name: "Wishlist (1)" })).toBeVisible();

  await page.getByRole("link", { name: "Wishlist (1)" }).click();
  await expect(page.getByRole("heading", { name: "Wishlist" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Saved products" }).getByRole("link", { name: "Brass Compass" })).toBeVisible();
  await expect(page.locator("#sf-saved .price")).toHaveText("$42.00");

  await page.reload();
  await expect(page.getByRole("link", { name: "Wishlist (1)" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Saved products" }).getByRole("link", { name: "Brass Compass" })).toBeVisible();
});

test("removes a saved product from the wishlist", async ({ page }) => {
  await page.goto("/products/1");
  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(page.getByRole("link", { name: "Wishlist (1)" })).toBeVisible();

  await page.goto("/wishlist");
  await page.getByRole("button", { name: "Remove Field Notebook" }).click();

  await expect(page.getByRole("link", { name: "Wishlist (0)" })).toBeVisible();
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();
  await expect(page.getByRole("list", { name: "Saved products" }).getByRole("link", { name: "Field Notebook" })).toHaveCount(0);
});

test("shows product not found for an unknown product URL", async ({ page }) => {
  const response = await page.goto("/products/99");

  expect(response.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Product not found" })).toBeVisible();
});

import { expect, test } from "@playwright/test";

const products = [
  { name: "Field Notebook", price: "$9.50" },
  { name: "Brass Compass", price: "$42.00" },
  { name: "Wool Blanket", price: "$68.00" },
];

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("product list links to detail pages with each product name and price", async ({ page }) => {
  await page.goto("/");

  for (const product of products) {
    await page.getByRole("link", { name: product.name }).click();
    await expect(page.getByRole("heading", { name: product.name })).toBeVisible();
    await expect(page.locator("#sf-product-price")).toHaveText(product.price);
    await page.getByRole("link", { name: "Back to products" }).click();
  }
});

test("wishlist count follows saved products across pages and reloads", async ({ page }) => {
  await page.goto("/products/1");
  await expect(page.locator("#sf-wishlist-count")).toHaveText("0");

  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  await expect(page.locator("#sf-wishlist-count")).toHaveText("1");

  await page.goto("/");
  await expect(page.locator("#sf-wishlist-count")).toHaveText("1");

  await page.goto("/wishlist");
  await expect(page.locator("#sf-wishlist-count")).toHaveText("1");
  await expect(page.getByRole("link", { name: "Field Notebook" })).toBeVisible();
  await expect(page.locator("#sf-saved .price")).toHaveText("$9.50");

  await page.reload();
  await expect(page.locator("#sf-wishlist-count")).toHaveText("1");
  await expect(page.getByRole("link", { name: "Field Notebook" })).toBeVisible();
});

test("removing a saved product updates the wishlist page", async ({ page }) => {
  await page.goto("/products/1");
  await page.getByRole("button", { name: "Add to wishlist" }).click();

  await page.goto("/wishlist");
  await page.getByRole("button", { name: "Remove Field Notebook" }).click();

  await expect(page.locator("#sf-wishlist-count")).toHaveText("0");
  await expect(page.getByRole("link", { name: "Field Notebook" })).toHaveCount(0);
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();
});

test("unknown product URLs show the product not found page", async ({ page }) => {
  const response = await page.goto("/products/99");

  expect(response.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Product not found" })).toBeVisible();
});

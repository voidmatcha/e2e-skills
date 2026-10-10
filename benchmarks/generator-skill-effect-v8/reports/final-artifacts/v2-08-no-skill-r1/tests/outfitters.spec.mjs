import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("product list links to each product detail page with its price", async ({ page }) => {
  const products = [
    { name: "Field Notebook", price: "$9.50" },
    { name: "Brass Compass", price: "$42.00" },
    { name: "Wool Blanket", price: "$68.00" },
  ];

  await page.goto("/");

  for (const product of products) {
    await page.getByRole("link", { name: product.name }).click();
    await expect(page.getByRole("heading", { name: product.name })).toBeVisible();
    await expect(page.getByText(product.price)).toBeVisible();
    await page.getByRole("link", { name: "Back to products" }).click();
  }
});

test("wishlist count updates across pages and saved products persist after reload", async ({ page }) => {
  await page.goto("/products/1");

  await expect(page.getByRole("link", { name: "Wishlist (0)" })).toBeVisible();
  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  await expect(page.getByRole("link", { name: "Wishlist (1)" })).toBeVisible();

  await page.goto("/");
  await expect(page.getByRole("link", { name: "Wishlist (1)" })).toBeVisible();

  await page.goto("/wishlist");
  await expect(page.getByRole("link", { name: "Wishlist (1)" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Saved products" })).toContainText("Field Notebook");
  await expect(page.getByText("$9.50")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("link", { name: "Wishlist (1)" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Saved products" })).toContainText("Field Notebook");
});

test("removing a saved product updates the wishlist page and header count", async ({ page }) => {
  await page.goto("/products/1");
  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(page.getByRole("link", { name: "Wishlist (1)" })).toBeVisible();

  await page.goto("/wishlist");
  await page.getByRole("button", { name: "Remove Field Notebook" }).click();

  await expect(page.getByRole("link", { name: "Wishlist (0)" })).toBeVisible();
  await expect(page.getByText("Field Notebook")).toBeHidden();
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();
});

test("unknown product URL shows the product not found page", async ({ page }) => {
  const response = await page.goto("/products/99");

  expect(response.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Product not found" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to products" })).toBeVisible();
});

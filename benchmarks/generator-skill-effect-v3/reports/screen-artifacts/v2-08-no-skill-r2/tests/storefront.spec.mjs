import { expect, test } from "@playwright/test";

const PRODUCTS = [
  { id: 1, name: "Field Notebook", price: "$9.50" },
  { id: 2, name: "Brass Compass", price: "$42.00" },
  { id: 3, name: "Wool Blanket", price: "$68.00" },
];

const wishlistLink = (page) => page.getByRole("link", { name: /^Wishlist \(\d+\)$/ });

test.beforeEach(async ({ request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
});

test("product list links to each product's page with its name and price", async ({ page }) => {
  await page.goto("/");
  for (const product of PRODUCTS) {
    await page.goto("/");
    const item = page.getByRole("listitem").filter({ hasText: product.name });
    await expect(item).toContainText(product.price);
    await item.getByRole("link", { name: product.name }).click();
    await expect(page).toHaveURL(`/products/${product.id}`);
    await expect(page.getByRole("heading", { name: product.name })).toBeVisible();
    await expect(page.getByText(product.price)).toBeVisible();
  }
});

test("adding to the wishlist updates the header count on every page", async ({ page }) => {
  await page.goto("/products/2");
  await expect(wishlistLink(page)).toHaveText("Wishlist (0)");
  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");

  await page.goto("/");
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
  await page.goto("/products/3");
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
  await page.goto("/wishlist");
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
  await page.goto("/products/99");
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
});

test("adding the same product twice does not increase the count", async ({ page }) => {
  await page.goto("/products/1");
  const add = page.getByRole("button", { name: "Add to wishlist" });
  await add.click();
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
  await add.click();
  await expect(page.getByRole("status")).toHaveText("Already in your wishlist");
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
});

test("wishlist page lists saved products", async ({ page }) => {
  await page.goto("/wishlist");
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();

  for (const id of [1, 3]) {
    await page.goto(`/products/${id}`);
    await page.getByRole("button", { name: "Add to wishlist" }).click();
    await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  }

  await page.goto("/wishlist");
  const saved = page.getByRole("list", { name: "Saved products" }).getByRole("listitem");
  await expect(saved).toHaveCount(2);
  await expect(saved.nth(0)).toContainText("Field Notebook");
  await expect(saved.nth(0)).toContainText("$9.50");
  await expect(saved.nth(1)).toContainText("Wool Blanket");
  await expect(saved.nth(1)).toContainText("$68.00");
  await expect(page.getByText("Your wishlist is empty")).toBeHidden();
});

test("removing a product takes it off the wishlist and persists after reload", async ({ page }) => {
  for (const id of [1, 2]) {
    await page.goto(`/products/${id}`);
    await page.getByRole("button", { name: "Add to wishlist" }).click();
    await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  }

  await page.goto("/wishlist");
  const saved = page.getByRole("list", { name: "Saved products" }).getByRole("listitem");
  await expect(saved).toHaveCount(2);

  await page.getByRole("button", { name: "Remove Field Notebook" }).click();
  await expect(saved).toHaveCount(1);
  await expect(saved.first()).toContainText("Brass Compass");
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");

  await page.reload();
  await expect(saved).toHaveCount(1);
  await expect(saved.first()).toContainText("Brass Compass");
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");

  await page.getByRole("button", { name: "Remove Brass Compass" }).click();
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();
  await page.reload();
  await expect(saved).toHaveCount(0);
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();
  await expect(wishlistLink(page)).toHaveText("Wishlist (0)");
});

test("saved wishlist survives a reload of the product page", async ({ page }) => {
  await page.goto("/products/3");
  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
  await page.reload();
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
  await page.goto("/wishlist");
  await expect(page.getByRole("link", { name: "Wool Blanket" })).toBeVisible();
});

test("an unknown product URL shows the not found page", async ({ page }) => {
  const response = await page.goto("/products/99");
  expect(response.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Product not found" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add to wishlist" })).toHaveCount(0);
});

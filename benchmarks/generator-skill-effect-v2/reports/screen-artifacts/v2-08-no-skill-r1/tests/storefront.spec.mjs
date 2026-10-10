import { expect, test } from "@playwright/test";

const PRODUCTS = [
  { id: 1, name: "Field Notebook", price: "$9.50" },
  { id: 2, name: "Brass Compass", price: "$42.00" },
  { id: 3, name: "Wool Blanket", price: "$68.00" },
];

test.beforeEach(async ({ request }) => {
  // The wishlist lives on the server, so start every test from an empty one.
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
});

const count = (page) => page.locator("#sf-wishlist-count");

test("product list links to each product's page with its name and price", async ({ page }) => {
  await page.goto("/");
  const items = page.getByRole("list", { name: "Products" }).getByRole("listitem");
  await expect(items).toHaveCount(PRODUCTS.length);

  for (const product of PRODUCTS) {
    await page.goto("/");
    const item = items.filter({ hasText: product.name });
    await expect(item).toContainText(product.price);
    await item.getByRole("link", { name: product.name }).click();
    await expect(page).toHaveURL(`/products/${product.id}`);
    await expect(page.getByRole("heading", { name: product.name })).toBeVisible();
    await expect(page.locator("#sf-product-price")).toHaveText(product.price);
  }
});

test("adding to the wishlist updates the header count on every page", async ({ page }) => {
  await page.goto("/");
  await expect(count(page)).toHaveText("0");

  await page.goto("/products/2");
  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  await expect(count(page)).toHaveText("1");

  await page.goto("/");
  await expect(count(page)).toHaveText("1");
  await page.goto("/products/3");
  await expect(count(page)).toHaveText("1");
  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(count(page)).toHaveText("2");

  await page.goto("/wishlist");
  await expect(count(page)).toHaveText("2");
  await page.goto("/products/99");
  await expect(count(page)).toHaveText("2");
});

test("adding the same product twice does not duplicate it", async ({ page }) => {
  await page.goto("/products/1");
  const add = page.getByRole("button", { name: "Add to wishlist" });
  await add.click();
  await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  await add.click();
  await expect(page.getByRole("status")).toHaveText("Already in your wishlist");
  await expect(count(page)).toHaveText("1");
});

test("wishlist page lists the saved products", async ({ page }) => {
  await page.goto("/wishlist");
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();
  await expect(page.getByRole("list", { name: "Saved products" }).getByRole("listitem")).toHaveCount(0);

  for (const id of [3, 1]) {
    await page.goto(`/products/${id}`);
    await page.getByRole("button", { name: "Add to wishlist" }).click();
    await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  }

  await page.goto("/wishlist");
  const saved = page.getByRole("list", { name: "Saved products" }).getByRole("listitem");
  await expect(saved).toHaveCount(2);
  await expect(saved.filter({ hasText: "Wool Blanket" })).toContainText("$68.00");
  await expect(saved.filter({ hasText: "Field Notebook" })).toContainText("$9.50");
  await expect(page.getByText("Your wishlist is empty")).toBeHidden();
});

test("Remove takes a product off the wishlist and persists after reload", async ({ page }) => {
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
  await expect(count(page)).toHaveText("1");

  await page.reload();
  await expect(saved).toHaveCount(1);
  await expect(saved.first()).toContainText("Brass Compass");
  await expect(count(page)).toHaveText("1");

  await page.getByRole("button", { name: "Remove Brass Compass" }).click();
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();
  await page.reload();
  await expect(saved).toHaveCount(0);
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();
  await expect(count(page)).toHaveText("0");
});

test("the wishlist is kept on the server across browser contexts", async ({ page, browser }) => {
  await page.goto("/products/1");
  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(count(page)).toHaveText("1");

  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await otherPage.goto("http://127.0.0.1:5732/wishlist");
  await expect(otherPage.getByRole("listitem").filter({ hasText: "Field Notebook" })).toBeVisible();
  await other.close();
});

test("an unknown product URL shows the Product not found page", async ({ page }) => {
  const response = await page.goto("/products/99");
  expect(response.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Product not found" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add to wishlist" })).toHaveCount(0);
  await page.getByRole("link", { name: "Back to products" }).click();
  await expect(page.getByRole("heading", { name: "Products" })).toBeVisible();
});

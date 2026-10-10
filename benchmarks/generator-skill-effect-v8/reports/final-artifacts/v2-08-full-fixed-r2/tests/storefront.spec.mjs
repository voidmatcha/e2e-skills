import { expect, test } from "@playwright/test";

const products = [
  { id: 1, name: "Field Notebook", price: "$9.50" },
  { id: 2, name: "Brass Compass", price: "$42.00" },
  { id: 3, name: "Wool Blanket", price: "$68.00" },
];

test.beforeEach(async ({ request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
});

test.afterEach(async ({ request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
});

test("links every product to its detail page with the right price", async ({ page }) => {
  for (const product of products) {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Products", exact: true })).toBeVisible();

    await page.getByRole("link", { name: product.name, exact: true }).click();

    await expect(page).toHaveURL(`/products/${product.id}`);
    await expect(page.getByRole("heading", { name: product.name, exact: true })).toBeVisible();
    await expect(page.getByText(product.price)).toBeVisible();
  }
});

test("saves a product to the wishlist until it is removed", async ({ page }) => {
  await page.goto("/products/1");

  const addRequestPromise = page.waitForRequest(
    (request) => request.method() === "POST" && new URL(request.url()).pathname === "/api/wishlist",
  );
  await page.getByRole("button", { name: "Add to wishlist", exact: true }).click();
  const addRequest = await addRequestPromise;

  expect(addRequest.postDataJSON()).toEqual({ id: 1 });
  await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  await expect(page.getByRole("link", { name: "Wishlist (1)", exact: true })).toBeVisible();

  await page.goto("/");
  await expect(page.getByRole("link", { name: "Wishlist (1)", exact: true })).toBeVisible();

  await page.goto("/wishlist");
  const savedProducts = page.getByRole("list", { name: "Saved products", exact: true });
  await expect(savedProducts.getByRole("listitem").filter({ hasText: "Field Notebook" })).toBeVisible();

  await page.reload();
  await expect(savedProducts.getByRole("listitem").filter({ hasText: "Field Notebook" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Wishlist (1)", exact: true })).toBeVisible();

  const removeRequestPromise = page.waitForRequest(
    (request) => request.method() === "DELETE" && new URL(request.url()).pathname === "/api/wishlist/1",
  );
  await page.getByRole("button", { name: "Remove Field Notebook", exact: true }).click();
  await removeRequestPromise;

  await page.reload();
  await expect(savedProducts.getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();
  await expect(page.getByRole("link", { name: "Wishlist (0)", exact: true })).toBeVisible();
});

test("shows a not found page for an unknown product", async ({ page }) => {
  await page.goto("/products/99");

  await expect(page.getByRole("heading", { name: "Product not found", exact: true })).toBeVisible();
});

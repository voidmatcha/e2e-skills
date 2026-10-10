import { expect, test } from "@playwright/test";

const products = [
  { id: 1, name: "Field Notebook", price: "$9.50" },
  { id: 2, name: "Brass Compass", price: "$42.00" },
  { id: 3, name: "Wool Blanket", price: "$68.00" },
];

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("links each product to its detail page", async ({ page }) => {
  for (const product of products) {
    await page.goto("/");
    await page.getByRole("link", { name: product.name, exact: true }).click();

    await expect(page.getByRole("heading", { name: product.name, exact: true })).toBeVisible();
    await expect(page.getByText(product.price)).toBeVisible();
  }
});

test("adds a product to the wishlist and keeps it after reload", async ({ page }) => {
  await page.goto("/products/1");

  const addRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/api/wishlist"),
  );
  const addResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().endsWith("/api/wishlist"),
  );

  await page.getByRole("button", { name: "Add to wishlist", exact: true }).click();

  const request = await addRequest;
  expect(request.postDataJSON()).toEqual({ id: 1 });
  await expect.poll(async () => (await addResponse).status()).toBe(200);
  await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  await expect(page.getByRole("link", { name: /^Wishlist \(1\)$/ })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("link", { name: /^Wishlist \(1\)$/ })).toBeVisible();

  await page.goto("/wishlist");
  await expect(page.getByRole("heading", { name: "Wishlist", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Field Notebook", exact: true })).toBeVisible();
  await expect(page.getByText("$9.50")).toBeVisible();
  await expect(page.getByRole("link", { name: /^Wishlist \(1\)$/ })).toBeVisible();
});

test("removes a saved product from the wishlist", async ({ page }) => {
  await page.goto("/products/2");

  await page.getByRole("button", { name: "Add to wishlist", exact: true }).click();
  await expect(page.getByRole("link", { name: /^Wishlist \(1\)$/ })).toBeVisible();

  await page.goto("/wishlist");
  const savedProducts = page.getByRole("list", { name: "Saved products", exact: true });
  await expect(page.getByRole("link", { name: "Brass Compass", exact: true })).toBeVisible();

  const removeRequest = page.waitForRequest(
    (request) => request.method() === "DELETE" && request.url().endsWith("/api/wishlist/2"),
  );

  await page.getByRole("button", { name: "Remove Brass Compass", exact: true }).click();
  await removeRequest;

  await expect(savedProducts.getByRole("listitem")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /^Wishlist \(0\)$/ })).toBeVisible();
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();

  await page.reload();
  await expect(savedProducts.getByRole("listitem")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /^Wishlist \(0\)$/ })).toBeVisible();
});

test("shows product not found for an unknown product", async ({ page }) => {
  await page.goto("/products/99");

  await expect(page.getByRole("heading", { name: "Product not found", exact: true })).toBeVisible();
});

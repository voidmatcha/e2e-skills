import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("opens a product page from the product list", async ({ page }) => {
  await page.goto("/");

  await page
    .getByRole("list", { name: "Products" })
    .getByRole("link", { name: /^Brass Compass$/ })
    .click();

  await expect(page.getByRole("heading", { name: /^Brass Compass$/ })).toBeVisible();
  await expect(page.getByText("$42.00")).toBeVisible();
});

test("adds a product to the wishlist and keeps it after reload", async ({ page }) => {
  await page.goto("/products/2");

  const wishlistRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && new URL(request.url()).pathname === "/api/wishlist";
  });
  await page.getByRole("button", { name: /^Add to wishlist$/ }).click();
  const request = await wishlistRequest;

  expect(request.postDataJSON()).toEqual({ id: 2 });
  await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  await expect(page.getByRole("link", { name: /^Wishlist \(1\)$/ })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("link", { name: /^Wishlist \(1\)$/ })).toBeVisible();

  await page.goto("/");
  await expect(page.getByRole("link", { name: /^Wishlist \(1\)$/ })).toBeVisible();

  await page.getByRole("link", { name: /^Wishlist \(1\)$/ }).click();
  await expect(
    page.getByRole("list", { name: "Saved products" }).getByRole("link", { name: /^Brass Compass$/ }),
  ).toBeVisible();
});

test("removes a saved product from the wishlist", async ({ page, request }) => {
  await request.post("/api/wishlist", { data: { id: 1 } });
  await request.post("/api/wishlist", { data: { id: 3 } });
  await page.goto("/wishlist");

  const removalRequest = page.waitForRequest((request) => {
    return request.method() === "DELETE" && new URL(request.url()).pathname === "/api/wishlist/1";
  });
  await page.getByRole("button", { name: /^Remove Field Notebook$/ }).click();
  const removed = await removalRequest;

  expect(new URL(removed.url()).pathname).toBe("/api/wishlist/1");
  await expect(page.getByRole("link", { name: /^Wishlist \(1\)$/ })).toBeVisible();
  await expect(
    page.getByRole("list", { name: "Saved products" }).getByRole("listitem").filter({ hasText: "Field Notebook" }),
  ).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("link", { name: /^Wishlist \(1\)$/ })).toBeVisible();
  await expect(
    page.getByRole("list", { name: "Saved products" }).getByRole("link", { name: /^Wool Blanket$/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("list", { name: "Saved products" }).getByRole("listitem").filter({ hasText: "Field Notebook" }),
  ).toHaveCount(0);
});

test("shows not found for an unknown product", async ({ page }) => {
  await page.goto("/products/99");

  await expect(page.getByRole("heading", { name: /^Product not found$/ })).toBeVisible();
});

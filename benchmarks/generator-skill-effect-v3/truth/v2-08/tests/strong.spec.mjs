import { expect, test } from "@playwright/test";

const wishlistLink = (page) => page.getByRole("link", { name: /Wishlist \(\d+\)/ });
const saved = (page) => page.getByRole("list", { name: "Saved products" }).getByRole("listitem");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("each product page shows its own name and price", async ({ page }) => {
  for (const [name, price] of [["Field Notebook", "$9.50"], ["Brass Compass", "$42.00"], ["Wool Blanket", "$68.00"]]) {
    await page.goto("/");
    await page.getByRole("list", { name: "Products" }).getByRole("link", { name }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(name);
    await expect(page.getByText(price)).toBeVisible();
  }
});

test("adding updates the header count on every page and the wishlist page", async ({ page }) => {
  await page.getByRole("link", { name: "Brass Compass" }).click();
  await page.getByRole("button", { name: "Add to wishlist" }).click();
  await expect(page.getByRole("status")).toHaveText("Added to your wishlist");
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
  await page.goto("/");
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
  await wishlistLink(page).click();
  await expect(page).toHaveURL(/\/wishlist$/);
  await expect(saved(page)).toHaveText([/Brass Compass/]);
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
});

test("remove takes the product off on the server", async ({ page }) => {
  await page.request.post("/api/wishlist", { data: { id: 1 } });
  await page.request.post("/api/wishlist", { data: { id: 3 } });
  await page.goto("/wishlist");
  await expect(saved(page)).toHaveCount(2);
  await page.getByRole("button", { name: "Remove Field Notebook" }).click();
  await expect(saved(page)).toHaveText([/Wool Blanket/]);
  await expect(wishlistLink(page)).toHaveText("Wishlist (1)");
  await page.reload();
  await expect(saved(page)).toHaveText([/Wool Blanket/]);
  await page.getByRole("button", { name: "Remove Wool Blanket" }).click();
  await expect(saved(page)).toHaveCount(0);
  await expect(page.getByText("Your wishlist is empty")).toBeVisible();
});

test("an unknown product shows the not-found page", async ({ page }) => {
  const response = await page.goto("/products/99");
  expect(response.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Product not found" })).toBeVisible();
  await page.getByRole("link", { name: "Back to products" }).click();
  await expect(page.getByRole("heading", { name: "Products" })).toBeVisible();
});

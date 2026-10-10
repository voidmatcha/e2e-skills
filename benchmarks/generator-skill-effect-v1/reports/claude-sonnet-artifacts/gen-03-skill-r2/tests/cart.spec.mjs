import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await page.goto("/");
});

const add = (page, name) => page.getByRole("button", { name: `Add ${name} to cart` }).click();

test("starts with an empty cart", async ({ page }) => {
  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await expect(page.getByText("Total: $0.00")).toBeVisible();
  await expect(page.getByRole("list", { name: "Cart" }).getByRole("listitem")).toHaveCount(0);
});

test("add to cart creates a line with quantity 1", async ({ page }) => {
  await add(page, "Canvas Tote");

  const tote = page.getByRole("list", { name: "Cart" }).getByRole("listitem");
  await expect(tote).toHaveCount(1);
  await expect(tote).toContainText("Canvas Tote");
  await expect(tote).toContainText("Qty: 1");
  await expect(page.getByText("Your cart is empty")).toBeHidden();
  await expect(page.getByText("Total: $25.00")).toBeVisible();
});

test("+ and − change the quantity and it never drops below 1", async ({ page }) => {
  await add(page, "Camp Mug");
  const mug = page.getByRole("list", { name: "Cart" }).getByRole("listitem");

  await page.getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(mug).toContainText("Qty: 2");
  await page.getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(mug).toContainText("Qty: 3");

  await page.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await expect(mug).toContainText("Qty: 2");
  await page.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await expect(mug).toContainText("Qty: 1");

  await page.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await expect(mug).toContainText("Qty: 1");
  await expect(mug).toHaveCount(1);
  await expect(page.getByText("Total: $12.50")).toBeVisible();
});

test("total is the sum of price times quantity over all lines", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Merino Beanie");
  await add(page, "Camp Mug");
  await expect(page.getByText("Total: $67.50")).toBeVisible();

  await page.getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await page.getByRole("button", { name: "Increase quantity of Canvas Tote" }).click();
  await page.getByRole("button", { name: "Increase quantity of Canvas Tote" }).click();
  // 3 x 25.00 + 1 x 30.00 + 2 x 12.50
  await expect(page.getByText("Total: $130.00")).toBeVisible();

  await page.getByRole("button", { name: "Decrease quantity of Canvas Tote" }).click();
  // 2 x 25.00 + 1 x 30.00 + 2 x 12.50
  await expect(page.getByText("Total: $105.00")).toBeVisible();
});

test("remove deletes only that line and updates the total", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Merino Beanie");
  const cart = page.getByRole("list", { name: "Cart" }).getByRole("listitem");
  await expect(cart).toHaveCount(2);

  await page.getByRole("button", { name: "Remove Canvas Tote" }).click();

  await expect(cart).toHaveCount(1);
  await expect(cart).toContainText("Merino Beanie");
  await expect(cart).not.toContainText("Canvas Tote");
  await expect(page.getByText("Total: $30.00")).toBeVisible();
  await expect(page.getByText("Your cart is empty")).toBeHidden();
});

test("removing the last line shows the empty message", async ({ page }) => {
  await add(page, "Merino Beanie");
  await expect(page.getByText("Your cart is empty")).toBeHidden();

  await page.getByRole("button", { name: "Remove Merino Beanie" }).click();

  await expect(page.getByRole("list", { name: "Cart" }).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await expect(page.getByText("Total: $0.00")).toBeVisible();
});

test("the cart is stored on the server and survives a reload", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Camp Mug");
  await page.getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(page.getByText("Total: $50.00")).toBeVisible();

  await page.reload();

  const cart = page.getByRole("list", { name: "Cart" }).getByRole("listitem");
  await expect(cart).toHaveCount(2);
  await expect(cart.filter({ hasText: "Canvas Tote" })).toContainText("Qty: 1");
  await expect(cart.filter({ hasText: "Camp Mug" })).toContainText("Qty: 2");
  await expect(page.getByText("Total: $50.00")).toBeVisible();
  await expect(page.getByText("Your cart is empty")).toBeHidden();
});

test("a removal persists across reload and shows the empty message", async ({ page }) => {
  await add(page, "Canvas Tote");
  await page.getByRole("button", { name: "Remove Canvas Tote" }).click();
  await expect(page.getByText("Your cart is empty")).toBeVisible();

  await page.reload();

  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await expect(page.getByRole("list", { name: "Cart" }).getByRole("listitem")).toHaveCount(0);
});

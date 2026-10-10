import { expect, test } from "@playwright/test";

const lineFor = (page, name) =>
  page.getByRole("list", { name: "Cart" }).getByRole("listitem").filter({ hasText: name });

const addToCart = (page, name) => page.getByRole("button", { name: `Add ${name} to cart` }).click();

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("Your cart is empty")).toBeVisible();
});

test("starts with an empty cart and a zero total", async ({ page }) => {
  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await expect(page.getByText("Total: $0.00")).toBeVisible();
  await expect(page.getByRole("list", { name: "Cart" }).getByRole("listitem")).toHaveCount(0);
});

test("add to cart adds a line with quantity 1", async ({ page }) => {
  await addToCart(page, "Canvas Tote");
  const line = lineFor(page, "Canvas Tote");
  await expect(line).toHaveCount(1);
  await expect(line).toContainText("Qty: 1");
  await expect(page.getByText("Your cart is empty")).toBeHidden();
  await expect(page.getByText("Total: $25.00")).toBeVisible();
});

test("+ and − change the quantity and it never goes below 1", async ({ page }) => {
  await addToCart(page, "Camp Mug");
  const line = lineFor(page, "Camp Mug");
  await line.getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(line).toContainText("Qty: 2");
  await line.getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(line).toContainText("Qty: 3");
  await line.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await expect(line).toContainText("Qty: 2");
  await line.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await expect(line).toContainText("Qty: 1");
  await line.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await expect(line).toContainText("Qty: 1");
  await expect(line).toHaveCount(1);
});

test("total is the sum of price times quantity over all lines", async ({ page }) => {
  await addToCart(page, "Canvas Tote");
  await addToCart(page, "Merino Beanie");
  await addToCart(page, "Camp Mug");
  await expect(page.getByText("Total: $67.50")).toBeVisible();

  await lineFor(page, "Camp Mug").getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(page.getByText("Total: $80.00")).toBeVisible();

  await lineFor(page, "Canvas Tote").getByRole("button", { name: "Increase quantity of Canvas Tote" }).click();
  await lineFor(page, "Canvas Tote").getByRole("button", { name: "Increase quantity of Canvas Tote" }).click();
  await expect(lineFor(page, "Canvas Tote")).toContainText("Qty: 3");
  await expect(page.getByText("Total: $130.00")).toBeVisible();

  await lineFor(page, "Canvas Tote").getByRole("button", { name: "Decrease quantity of Canvas Tote" }).click();
  await expect(page.getByText("Total: $105.00")).toBeVisible();
});

test("remove deletes the line and updates the total", async ({ page }) => {
  await addToCart(page, "Canvas Tote");
  await addToCart(page, "Camp Mug");
  await lineFor(page, "Canvas Tote").getByRole("button", { name: "Remove Canvas Tote" }).click();
  await expect(lineFor(page, "Canvas Tote")).toHaveCount(0);
  await expect(lineFor(page, "Camp Mug")).toHaveCount(1);
  await expect(page.getByText("Total: $12.50")).toBeVisible();
  await expect(page.getByText("Your cart is empty")).toBeHidden();
});

test("removing the last line shows the empty message", async ({ page }) => {
  await addToCart(page, "Merino Beanie");
  await lineFor(page, "Merino Beanie").getByRole("button", { name: "Remove Merino Beanie" }).click();
  await expect(page.getByRole("list", { name: "Cart" }).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await expect(page.getByText("Total: $0.00")).toBeVisible();
});

test("the cart is stored on the server and survives a reload", async ({ page }) => {
  await addToCart(page, "Canvas Tote");
  await addToCart(page, "Camp Mug");
  await lineFor(page, "Camp Mug").getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(lineFor(page, "Camp Mug")).toContainText("Qty: 2");

  await page.reload();
  await expect(lineFor(page, "Canvas Tote")).toContainText("Qty: 1");
  await expect(lineFor(page, "Camp Mug")).toContainText("Qty: 2");
  await expect(page.getByText("Total: $50.00")).toBeVisible();
  await expect(page.getByText("Your cart is empty")).toBeHidden();
});

test("a removed line stays removed after a reload", async ({ page }) => {
  await addToCart(page, "Canvas Tote");
  await lineFor(page, "Canvas Tote").getByRole("button", { name: "Remove Canvas Tote" }).click();
  await expect(page.getByText("Your cart is empty")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await expect(page.getByRole("list", { name: "Cart" }).getByRole("listitem")).toHaveCount(0);
});

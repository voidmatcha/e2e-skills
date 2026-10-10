import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("Your cart is empty")).toBeVisible();
});

const cart = (page) => page.getByRole("list", { name: "Cart" });
const line = (page, name) => cart(page).getByRole("listitem").filter({ hasText: name });
const add = (page, name) => page.getByRole("button", { name: `Add ${name} to cart` }).click();

test("lists the catalog with prices", async ({ page }) => {
  const products = page.getByRole("list", { name: "Catalog" }).getByRole("listitem");
  await expect(products).toHaveCount(3);
  await expect(products.nth(0)).toContainText("Canvas Tote — $25.00");
  await expect(products.nth(1)).toContainText("Merino Beanie — $30.00");
  await expect(products.nth(2)).toContainText("Camp Mug — $12.50");
});

test("add to cart adds a line with quantity 1", async ({ page }) => {
  await add(page, "Canvas Tote");
  await expect(cart(page).getByRole("listitem")).toHaveCount(1);
  await expect(line(page, "Canvas Tote")).toContainText("Qty: 1");
  await expect(page.getByText("Your cart is empty")).toBeHidden();
  await expect(page.getByText("Total: $25.00")).toBeVisible();
});

test("+ and − change quantity and never go below 1", async ({ page }) => {
  await add(page, "Camp Mug");
  const mug = line(page, "Camp Mug");
  await mug.getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(mug).toContainText("Qty: 2");
  await mug.getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(mug).toContainText("Qty: 3");
  await mug.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await expect(mug).toContainText("Qty: 2");
  await mug.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await expect(mug).toContainText("Qty: 1");
  await mug.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await expect(mug).toContainText("Qty: 1");
  await expect(cart(page).getByRole("listitem")).toHaveCount(1);
});

test("total sums price times quantity over all lines", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Merino Beanie");
  await add(page, "Camp Mug");
  await expect(page.getByText("Total: $67.50")).toBeVisible();

  await line(page, "Camp Mug").getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await line(page, "Canvas Tote").getByRole("button", { name: "Increase quantity of Canvas Tote" }).click();
  await line(page, "Canvas Tote").getByRole("button", { name: "Increase quantity of Canvas Tote" }).click();
  // 25*3 + 30*1 + 12.5*2
  await expect(page.getByText("Total: $130.00")).toBeVisible();
});

test("remove deletes the line and updates the total", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Camp Mug");
  await line(page, "Canvas Tote").getByRole("button", { name: "Remove Canvas Tote" }).click();
  await expect(line(page, "Canvas Tote")).toHaveCount(0);
  await expect(line(page, "Camp Mug")).toHaveCount(1);
  await expect(page.getByText("Total: $12.50")).toBeVisible();
});

test("cart is stored on the server and survives reload", async ({ page }) => {
  await add(page, "Merino Beanie");
  await add(page, "Camp Mug");
  await line(page, "Camp Mug").getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(line(page, "Camp Mug")).toContainText("Qty: 2");

  await page.reload();
  await expect(cart(page).getByRole("listitem")).toHaveCount(2);
  await expect(line(page, "Merino Beanie")).toContainText("Qty: 1");
  await expect(line(page, "Camp Mug")).toContainText("Qty: 2");
  await expect(page.getByText("Total: $55.00")).toBeVisible();
});

test("removed lines stay removed after reload", async ({ page }) => {
  await add(page, "Canvas Tote");
  await line(page, "Canvas Tote").getByRole("button", { name: "Remove Canvas Tote" }).click();
  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await expect(cart(page).getByRole("listitem")).toHaveCount(0);
});

test("shows the empty message after the last line is removed", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Camp Mug");
  await expect(page.getByText("Your cart is empty")).toBeHidden();

  await line(page, "Canvas Tote").getByRole("button", { name: "Remove Canvas Tote" }).click();
  await expect(page.getByText("Your cart is empty")).toBeHidden();
  await line(page, "Camp Mug").getByRole("button", { name: "Remove Camp Mug" }).click();

  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await expect(page.getByText("Total: $0.00")).toBeVisible();
});

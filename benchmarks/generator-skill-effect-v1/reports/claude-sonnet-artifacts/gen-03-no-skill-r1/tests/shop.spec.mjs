import { expect, test } from "@playwright/test";

const line = (page, name) => page.getByRole("listitem").filter({ hasText: name, has: page.getByRole("button", { name: "Remove " + name }) });
const add = (page, name) => page.getByRole("button", { name: `Add ${name} to cart` }).click();
const lines = (page) => page.getByRole("list", { name: "Cart" }).getByRole("listitem");

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByText("Your cart is empty")).toBeVisible();
});

test("lists the catalog with prices", async ({ page }) => {
  const products = page.getByRole("list", { name: "Catalog" }).getByRole("listitem");
  await expect(products).toHaveCount(3);
  await expect(products.nth(0)).toContainText("Canvas Tote — $25.00");
  await expect(products.nth(1)).toContainText("Merino Beanie — $30.00");
  await expect(products.nth(2)).toContainText("Camp Mug — $12.50");
});

test("add to cart adds a line with Qty: 1", async ({ page }) => {
  await add(page, "Canvas Tote");
  await expect(lines(page)).toHaveCount(1);
  await expect(line(page, "Canvas Tote")).toContainText("Qty: 1");
  await expect(page.getByText("Your cart is empty")).toBeHidden();
  await expect(page.getByText("Total: $25.00")).toBeVisible();
});

test("+ and − change quantity, never below 1", async ({ page }) => {
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
  await expect(lines(page)).toHaveCount(1);
});

test("total is the sum of price times quantity", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Merino Beanie");
  await add(page, "Camp Mug");
  await expect(page.getByText("Total: $67.50")).toBeVisible();

  await line(page, "Camp Mug").getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(page.getByText("Total: $80.00")).toBeVisible();

  await line(page, "Merino Beanie").getByRole("button", { name: "Increase quantity of Merino Beanie" }).click();
  await line(page, "Merino Beanie").getByRole("button", { name: "Increase quantity of Merino Beanie" }).click();
  await expect(page.getByText("Total: $140.00")).toBeVisible();

  await line(page, "Merino Beanie").getByRole("button", { name: "Decrease quantity of Merino Beanie" }).click();
  await expect(page.getByText("Total: $110.00")).toBeVisible();
});

test("remove deletes the line and updates the total", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Camp Mug");
  await expect(lines(page)).toHaveCount(2);
  await page.getByRole("button", { name: "Remove Canvas Tote" }).click();
  await expect(lines(page)).toHaveCount(1);
  await expect(page.getByText("Canvas Tote", { exact: true })).toHaveCount(0);
  await expect(line(page, "Camp Mug")).toContainText("Qty: 1");
  await expect(page.getByText("Total: $12.50")).toBeVisible();
  await expect(page.getByText("Your cart is empty")).toBeHidden();
});

test("cart persists on the server across reload", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Merino Beanie");
  await line(page, "Merino Beanie").getByRole("button", { name: "Increase quantity of Merino Beanie" }).click();
  await expect(page.getByText("Total: $85.00")).toBeVisible();

  await page.reload();
  await expect(lines(page)).toHaveCount(2);
  await expect(line(page, "Canvas Tote")).toContainText("Qty: 1");
  await expect(line(page, "Merino Beanie")).toContainText("Qty: 2");
  await expect(page.getByText("Total: $85.00")).toBeVisible();
});

test("removal persists across reload", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Camp Mug");
  await page.getByRole("button", { name: "Remove Canvas Tote" }).click();
  await expect(lines(page)).toHaveCount(1);
  await page.reload();
  await expect(lines(page)).toHaveCount(1);
  await expect(line(page, "Camp Mug")).toBeVisible();
  await expect(page.getByText("Total: $12.50")).toBeVisible();
});

test("shows empty message after the last line is removed", async ({ page }) => {
  await add(page, "Canvas Tote");
  await expect(page.getByText("Your cart is empty")).toBeHidden();
  await page.getByRole("button", { name: "Remove Canvas Tote" }).click();
  await expect(lines(page)).toHaveCount(0);
  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await expect(page.getByText("Total: $0.00")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Your cart is empty")).toBeVisible();
});

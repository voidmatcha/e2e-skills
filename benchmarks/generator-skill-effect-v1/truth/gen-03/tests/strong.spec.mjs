import { expect, test } from "@playwright/test";

const lines = (page) => page.getByRole("list", { name: "Cart" }).getByRole("listitem");
const add = (page, name) => page.getByRole("button", { name: `Add ${name} to cart` }).click();

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds a line with quantity one", async ({ page }) => {
  await add(page, "Canvas Tote");
  await expect(lines(page)).toHaveCount(1);
  await expect(lines(page).first()).toContainText("Canvas Tote");
  await expect(lines(page).first()).toContainText("Qty: 1");
});

test("changes quantity and recomputes the total", async ({ page }) => {
  await add(page, "Camp Mug");
  await page.getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await page.getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(lines(page).first()).toContainText("Qty: 3");
  await expect(page.getByText("Total: $37.50")).toBeVisible();
  await page.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await expect(lines(page).first()).toContainText("Qty: 2");
  await expect(page.getByText("Total: $25.00")).toBeVisible();
});

test("never goes below one", async ({ page }) => {
  await add(page, "Merino Beanie");
  await page.getByRole("button", { name: "Decrease quantity of Merino Beanie" }).click();
  await expect(lines(page).first()).toContainText("Qty: 1");
  await expect(page.getByText("Total: $30.00")).toBeVisible();
});

test("sums several lines", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Merino Beanie");
  await expect(lines(page)).toHaveCount(2);
  await expect(page.getByText("Total: $55.00")).toBeVisible();
});

test("remove deletes the line on the server", async ({ page }) => {
  await add(page, "Canvas Tote");
  await add(page, "Camp Mug");
  await page.getByRole("button", { name: "Remove Canvas Tote" }).click();
  await expect(lines(page)).toHaveCount(1);
  await page.reload();
  await expect(lines(page)).toHaveCount(1);
  await expect(lines(page).first()).toContainText("Camp Mug");
});

test("keeps the cart across reloads", async ({ page }) => {
  await add(page, "Merino Beanie");
  await page.getByRole("button", { name: "Increase quantity of Merino Beanie" }).click();
  await expect(lines(page).first()).toContainText("Qty: 2");
  await page.reload();
  await expect(lines(page)).toHaveCount(1);
  await expect(lines(page).first()).toContainText("Qty: 2");
});

test("shows the empty state before and after", async ({ page }) => {
  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await add(page, "Camp Mug");
  await expect(page.getByText("Your cart is empty")).toBeHidden();
  await page.getByRole("button", { name: "Remove Camp Mug" }).click();
  await expect(lines(page)).toHaveCount(0);
  await expect(page.getByText("Your cart is empty")).toBeVisible();
  await expect(page.getByText("Total: $0.00")).toBeVisible();
});

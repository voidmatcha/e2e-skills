import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Shop" })).toBeVisible();
});

const lineFor = (page, name) =>
  page.getByRole("list", { name: "Cart" }).getByRole("listitem").filter({ hasText: name });
const addToCart = (page, name) => page.getByRole("button", { name: `Add ${name} to cart` });
const emptyMessage = (page) => page.getByText("Your cart is empty");
const total = (page) => page.getByText(/^Total:/);

test("shows an empty cart with a zero total before anything is added", async ({ page }) => {
  await expect(emptyMessage(page)).toBeVisible();
  await expect(total(page)).toHaveText("Total: $0.00");
});

test("adds a product to the cart with quantity 1", async ({ page }) => {
  await addToCart(page, "Canvas Tote").click();

  const line = lineFor(page, "Canvas Tote");
  await expect(line).toHaveCount(1);
  await expect(line).toContainText("Qty: 1");
  await expect(emptyMessage(page)).toBeHidden();
});

test("the + button increases the quantity of a line", async ({ page }) => {
  await addToCart(page, "Merino Beanie").click();
  const line = lineFor(page, "Merino Beanie");
  await expect(line).toContainText("Qty: 1");

  await line.getByRole("button", { name: "Increase quantity of Merino Beanie" }).click();

  await expect(line).toContainText("Qty: 2");
});

test("the − button decreases the quantity of a line", async ({ page }) => {
  await addToCart(page, "Merino Beanie").click();
  const line = lineFor(page, "Merino Beanie");
  await line.getByRole("button", { name: "Increase quantity of Merino Beanie" }).click();
  await expect(line).toContainText("Qty: 2");

  await line.getByRole("button", { name: "Decrease quantity of Merino Beanie" }).click();

  await expect(line).toContainText("Qty: 1");
});

test("the quantity never goes below 1", async ({ page }) => {
  await addToCart(page, "Camp Mug").click();
  const line = lineFor(page, "Camp Mug");
  await expect(line).toContainText("Qty: 1");

  // Wait for the server round trip so the assertion cannot pass before the click is processed
  const patched = page.waitForResponse(
    (r) => r.request().method() === "PATCH" && r.url().endsWith("/api/cart/items/mug"),
  );
  await line.getByRole("button", { name: "Decrease quantity of Camp Mug" }).click();
  await patched;

  await expect(line).toContainText("Qty: 1");
  await expect(line).not.toContainText("Qty: 0");
});

test("the total is the sum of price times quantity over all lines", async ({ page }) => {
  await addToCart(page, "Canvas Tote").click();
  await addToCart(page, "Camp Mug").click();
  await addToCart(page, "Merino Beanie").click();
  await expect(lineFor(page, "Merino Beanie")).toContainText("Qty: 1");

  await lineFor(page, "Canvas Tote").getByRole("button", { name: "Increase quantity of Canvas Tote" }).click();
  await expect(lineFor(page, "Canvas Tote")).toContainText("Qty: 2");
  await lineFor(page, "Camp Mug").getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(lineFor(page, "Camp Mug")).toContainText("Qty: 2");

  // 25.00 * 2 + 30.00 * 1 + 12.50 * 2
  await expect(total(page)).toHaveText("Total: $105.00");
});

test("Remove deletes only that line and updates the total", async ({ page }) => {
  await addToCart(page, "Canvas Tote").click();
  await addToCart(page, "Camp Mug").click();
  await expect(lineFor(page, "Camp Mug")).toHaveCount(1);
  await expect(total(page)).toHaveText("Total: $37.50");

  await lineFor(page, "Canvas Tote").getByRole("button", { name: "Remove Canvas Tote" }).click();

  await expect(lineFor(page, "Canvas Tote")).toHaveCount(0);
  await expect(lineFor(page, "Camp Mug")).toHaveCount(1);
  await expect(total(page)).toHaveText("Total: $12.50");
});

test("the cart is stored on the server so a reload shows the same lines", async ({ page }) => {
  await addToCart(page, "Canvas Tote").click();
  await addToCart(page, "Camp Mug").click();
  await lineFor(page, "Camp Mug").getByRole("button", { name: "Increase quantity of Camp Mug" }).click();
  await expect(lineFor(page, "Camp Mug")).toContainText("Qty: 2");
  await expect(total(page)).toHaveText("Total: $50.00");

  await page.reload();

  await expect(lineFor(page, "Camp Mug")).toContainText("Qty: 2");
  await expect(lineFor(page, "Canvas Tote")).toContainText("Qty: 1");
  await expect(lineFor(page, "Merino Beanie")).toHaveCount(0);
  await expect(total(page)).toHaveText("Total: $50.00");
});

test("shows the empty message after the last line is removed, also after a reload", async ({ page }) => {
  await addToCart(page, "Canvas Tote").click();
  await expect(lineFor(page, "Canvas Tote")).toHaveCount(1);
  await expect(emptyMessage(page)).toBeHidden();

  await lineFor(page, "Canvas Tote").getByRole("button", { name: "Remove Canvas Tote" }).click();

  await expect(lineFor(page, "Canvas Tote")).toHaveCount(0);
  await expect(emptyMessage(page)).toBeVisible();
  await expect(total(page)).toHaveText("Total: $0.00");

  await page.reload();

  await expect(emptyMessage(page)).toBeVisible();
  await expect(page.getByRole("list", { name: "Cart" }).getByRole("listitem")).toHaveCount(0);
});

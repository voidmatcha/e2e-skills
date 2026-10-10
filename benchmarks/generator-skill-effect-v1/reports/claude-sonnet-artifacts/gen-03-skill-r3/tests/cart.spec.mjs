import { expect, test } from "@playwright/test";

const isCartLoad = (response) =>
  response.url().endsWith("/api/cart") && response.request().method() === "GET";

test.describe("Shop cart", () => {
  test.beforeEach(async ({ page, request }) => {
    // The cart lives in server memory; reset it so every test starts empty.
    const reset = await request.post("/api/reset");
    expect(reset.ok()).toBeTruthy();

    // The page renders the cart after an async GET; wait for it so a late
    // response cannot overwrite state produced by the test's first click.
    const loaded = page.waitForResponse(isCartLoad);
    await page.goto("/");
    await loaded;
  });

  const addButton = (page, name) => page.getByRole("button", { name: `Add ${name} to cart` });
  const cartLine = (page, name) =>
    page.getByRole("list", { name: "Cart" }).getByRole("listitem").filter({ hasText: name });
  const total = (page, amount) => page.getByText(`Total: ${amount}`, { exact: true });
  const emptyMessage = (page) => page.getByText("Your cart is empty");

  test("shows an empty cart with a zero total initially", async ({ page }) => {
    await expect(emptyMessage(page)).toBeVisible();
    await expect(total(page, "$0.00")).toBeVisible();
  });

  test("adds a product to the cart with quantity 1", async ({ page }) => {
    const write = page.waitForRequest(
      (r) => r.method() === "POST" && r.url().endsWith("/api/cart/items"),
    );
    await addButton(page, "Canvas Tote").click();
    expect((await write).postDataJSON()).toEqual({ productId: "tote" });

    const line = cartLine(page, "Canvas Tote");
    await expect(line.getByText("Qty: 1")).toBeVisible();
    await expect(cartLine(page, "Canvas Tote")).toHaveCount(1);
    await expect(emptyMessage(page)).toBeHidden();
  });

  test("increases and decreases a line's quantity", async ({ page }) => {
    await addButton(page, "Merino Beanie").click();
    const line = cartLine(page, "Merino Beanie");
    await expect(line.getByText("Qty: 1")).toBeVisible();

    const patch = page.waitForRequest(
      (r) => r.method() === "PATCH" && r.url().endsWith("/api/cart/items/beanie"),
    );
    await line.getByRole("button", { name: "Increase quantity of Merino Beanie" }).click();
    expect((await patch).postDataJSON()).toEqual({ quantity: 2 });
    await expect(line.getByText("Qty: 2")).toBeVisible();

    await line.getByRole("button", { name: "Increase quantity of Merino Beanie" }).click();
    await expect(line.getByText("Qty: 3")).toBeVisible();

    await line.getByRole("button", { name: "Decrease quantity of Merino Beanie" }).click();
    await expect(line.getByText("Qty: 2")).toBeVisible();
  });

  test("never lets the quantity drop below 1", async ({ page }) => {
    await addButton(page, "Camp Mug").click();
    const line = cartLine(page, "Camp Mug");
    await expect(line.getByText("Qty: 1")).toBeVisible();

    const decrease = line.getByRole("button", { name: "Decrease quantity of Camp Mug" });
    const patched = page.waitForResponse((r) => r.request().method() === "PATCH");
    await decrease.click();
    await patched;
    await expect(line.getByText("Qty: 1")).toBeVisible();

    // A second decrease from the clamped state must still leave Qty: 1.
    const patchedAgain = page.waitForResponse((r) => r.request().method() === "PATCH");
    await decrease.click();
    expect(await (await patchedAgain).json()).toMatchObject([{ id: "mug", quantity: 1 }]);

    // Reload so the check reads server state, not the pre-click DOM.
    const reloaded = page.waitForResponse(isCartLoad);
    await page.reload();
    await reloaded;
    await expect(line.getByText("Qty: 1")).toBeVisible();
    await expect(total(page, "$12.50")).toBeVisible();
  });

  test("totals price times quantity across all lines", async ({ page }) => {
    await addButton(page, "Canvas Tote").click();
    await expect(cartLine(page, "Canvas Tote")).toHaveCount(1);
    await addButton(page, "Merino Beanie").click();
    await expect(cartLine(page, "Merino Beanie")).toHaveCount(1);
    await addButton(page, "Camp Mug").click();
    await expect(total(page, "$67.50")).toBeVisible();

    await cartLine(page, "Canvas Tote")
      .getByRole("button", { name: "Increase quantity of Canvas Tote" })
      .click();
    await expect(cartLine(page, "Canvas Tote").getByText("Qty: 2")).toBeVisible();

    // 2 x 25.00 + 1 x 30.00 + 1 x 12.50
    await expect(total(page, "$92.50")).toBeVisible();
  });

  test("removes only the chosen line", async ({ page }) => {
    await addButton(page, "Canvas Tote").click();
    await expect(cartLine(page, "Canvas Tote")).toHaveCount(1);
    await addButton(page, "Camp Mug").click();
    await expect(cartLine(page, "Camp Mug")).toHaveCount(1);

    const del = page.waitForRequest(
      (r) => r.method() === "DELETE" && r.url().endsWith("/api/cart/items/tote"),
    );
    await page.getByRole("button", { name: "Remove Canvas Tote" }).click();
    await del;

    await expect(cartLine(page, "Canvas Tote")).toHaveCount(0);
    await expect(cartLine(page, "Camp Mug")).toHaveCount(1);
    await expect(total(page, "$12.50")).toBeVisible();
  });

  test("keeps the same cart lines after a reload", async ({ page }) => {
    await addButton(page, "Canvas Tote").click();
    await expect(cartLine(page, "Canvas Tote")).toHaveCount(1);
    await addButton(page, "Camp Mug").click();
    await cartLine(page, "Camp Mug")
      .getByRole("button", { name: "Increase quantity of Camp Mug" })
      .click();
    await expect(cartLine(page, "Camp Mug").getByText("Qty: 2")).toBeVisible();

    await page.reload();

    await expect(cartLine(page, "Canvas Tote").getByText("Qty: 1")).toBeVisible();
    await expect(cartLine(page, "Camp Mug").getByText("Qty: 2")).toBeVisible();
    await expect(page.getByRole("list", { name: "Cart" }).getByRole("listitem")).toHaveCount(2);
    await expect(total(page, "$50.00")).toBeVisible();
    await expect(emptyMessage(page)).toBeHidden();
  });

  test("shows the empty message after the last line is removed", async ({ page }) => {
    await addButton(page, "Canvas Tote").click();
    await expect(cartLine(page, "Canvas Tote")).toHaveCount(1);
    await expect(emptyMessage(page)).toBeHidden();

    await page.getByRole("button", { name: "Remove Canvas Tote" }).click();

    await expect(emptyMessage(page)).toBeVisible();
    await expect(total(page, "$0.00")).toBeVisible();

    // The removal is stored on the server, not just hidden in the page.
    // The empty message is also the pre-load default, so wait for the cart GET.
    const reloaded = page.waitForResponse(isCartLoad);
    await page.reload();
    expect(await (await reloaded).json()).toEqual([]);
    await expect(emptyMessage(page)).toBeVisible();
    await expect(page.getByRole("list", { name: "Cart" }).getByRole("listitem")).toHaveCount(0);
  });
});

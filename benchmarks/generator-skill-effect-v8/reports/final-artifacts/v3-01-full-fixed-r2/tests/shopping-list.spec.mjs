import { expect, test } from "@playwright/test";

const seedItems = ["Oat milk", "Lemons", "Rye bread"];

async function resetList(request) {
  await expect(await request.post("/api/reset")).toBeOK();
}

function itemsList(page) {
  return page.getByRole("list", { name: "Items", exact: true });
}

function itemRow(page, name) {
  return itemsList(page)
    .getByRole("listitem")
    .filter({ has: page.getByRole("checkbox", { name: `Bought ${name}`, exact: true }) });
}

async function expectItemOrder(page, names) {
  await expect(itemsList(page).getByRole("listitem")).toHaveCount(names.length);

  for (const [index, name] of names.entries()) {
    const row = itemRow(page, name);
    await expect(row.getByText(String(index + 1), { exact: true })).toBeVisible();
    await expect(row).toContainText(name);
  }
}

test.describe("Shopping list", () => {
  test.beforeEach(async ({ page, request }) => {
    await resetList(request);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Shopping list", exact: true })).toBeVisible();
  });

  test("shows the seeded list with correct positions and move boundaries", async ({ page }) => {
    await expectItemOrder(page, seedItems);
    await expect(page.getByText("3 items · 0 bought")).toBeVisible();
    await expect(page.getByRole("button", { name: "Clear bought", exact: true })).toHaveCount(0);

    await expect(itemRow(page, "Oat milk").getByRole("button", { name: "Move Oat milk up", exact: true })).toBeDisabled();
    await expect(itemRow(page, "Rye bread").getByRole("button", { name: "Move Rye bread down", exact: true })).toBeDisabled();
  });

  test("adds an item at the end and keeps it after reload", async ({ page }) => {
    const addRequest = page.waitForRequest((request) => (
      request.method() === "POST" && request.url().endsWith("/api/items")
    ));

    await page.getByRole("textbox", { name: "New item", exact: true }).fill("Apples");
    await page.getByRole("button", { name: "Add", exact: true }).click();

    const request = await addRequest;
    expect(request.postDataJSON()).toEqual({ name: "Apples" });

    await expectItemOrder(page, [...seedItems, "Apples"]);
    await expect(page.getByText("4 items · 0 bought")).toBeVisible();

    await page.reload();
    await expectItemOrder(page, [...seedItems, "Apples"]);
  });

  test("moves items up and down while updating positions", async ({ page }) => {
    const moveDownRequest = page.waitForRequest((request) => (
      request.method() === "PUT" && request.url().endsWith("/api/order")
    ));

    await itemRow(page, "Lemons").getByRole("button", { name: "Move Lemons down", exact: true }).click();

    const downRequest = await moveDownRequest;
    expect(downRequest.postDataJSON().order).toHaveLength(3);

    await expectItemOrder(page, ["Oat milk", "Rye bread", "Lemons"]);
    await expect(itemRow(page, "Lemons").getByRole("button", { name: "Move Lemons down", exact: true })).toBeDisabled();

    await page.reload();
    await expectItemOrder(page, ["Oat milk", "Rye bread", "Lemons"]);

    const moveUpRequest = page.waitForRequest((request) => (
      request.method() === "PUT" && request.url().endsWith("/api/order")
    ));

    await itemRow(page, "Lemons").getByRole("button", { name: "Move Lemons up", exact: true }).click();

    const upRequest = await moveUpRequest;
    expect(upRequest.postDataJSON().order).toHaveLength(3);

    await expectItemOrder(page, seedItems);
  });

  test("marks bought items, clears them, and stores bought state across reload", async ({ page }) => {
    const boughtRequest = page.waitForRequest((request) => (
      request.method() === "PATCH" && /\/api\/items\/[^/]+$/.test(new URL(request.url()).pathname)
    ));

    await page.getByRole("checkbox", { name: "Bought Lemons", exact: true }).check();

    const request = await boughtRequest;
    expect(request.postDataJSON()).toEqual({ bought: true });

    await expect(page.getByText("3 items · 1 bought")).toBeVisible();
    await expect(page.getByRole("button", { name: "Clear bought", exact: true })).toBeVisible();

    await page.reload();
    await expect(page.getByRole("checkbox", { name: "Bought Lemons", exact: true })).toBeChecked();
    await expect(page.getByText("3 items · 1 bought")).toBeVisible();

    const clearRequest = page.waitForRequest((request) => (
      request.method() === "POST" && request.url().endsWith("/api/items/clear-bought")
    ));

    await page.getByRole("button", { name: "Clear bought", exact: true }).click();

    await clearRequest;
    await expect(page.getByText("2 items · 0 bought")).toBeVisible();
    await expect(itemRow(page, "Lemons")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Clear bought", exact: true })).toHaveCount(0);

    await page.reload();
    await expect(page.getByText("2 items · 0 bought")).toBeVisible();
    await expect(itemRow(page, "Lemons")).toHaveCount(0);
  });
});

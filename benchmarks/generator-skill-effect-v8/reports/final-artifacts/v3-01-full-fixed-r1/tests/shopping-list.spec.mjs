import { expect, test } from "@playwright/test";

const seededItems = ["Oat milk", "Lemons", "Rye bread"];

async function resetList(request) {
  await request.post("/api/reset");
}

function listItems(page) {
  return page.getByRole("list", { name: "Items", exact: true }).getByRole("listitem");
}

async function expectOrderedItems(page, names) {
  await expect(listItems(page)).toHaveText(
    names.map((name, index) => `${index + 1}${name}Move upMove down`),
  );
}

test.beforeEach(async ({ request }) => {
  await resetList(request);
});

test("shows the seeded shopping list with movement boundaries", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("3 items · 0 bought")).toBeVisible();
  await expectOrderedItems(page, seededItems);
  await expect(page.getByRole("button", { name: "Move Oat milk up", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Rye bread down", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Clear bought", exact: true })).toHaveCount(0);
});

test("adds an item at the end with the next position number", async ({ page }) => {
  await page.goto("/");

  const addRequest = page.waitForRequest(
    (request) => request.method() === "POST" && new URL(request.url()).pathname === "/api/items",
  );
  await page.getByLabel("New item").fill("Coffee beans");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const request = await addRequest;

  expect(request.postDataJSON()).toEqual({ name: "Coffee beans" });
  await expect(page.getByText("4 items · 0 bought")).toBeVisible();
  await expectOrderedItems(page, [...seededItems, "Coffee beans"]);
});

test("moves items up and down, updates positions, and keeps order after reload", async ({ page }) => {
  await page.goto("/");

  const moveDownRequest = page.waitForRequest(
    (request) => request.method() === "PUT" && new URL(request.url()).pathname === "/api/order",
  );
  await page.getByRole("button", { name: "Move Oat milk down", exact: true }).click();
  const downRequest = await moveDownRequest;

  expect(downRequest.postDataJSON()).toEqual({ order: [2, 1, 3] });
  await expectOrderedItems(page, ["Lemons", "Oat milk", "Rye bread"]);

  const moveUpRequest = page.waitForRequest(
    (request) => request.method() === "PUT" && new URL(request.url()).pathname === "/api/order",
  );
  await page.getByRole("button", { name: "Move Rye bread up", exact: true }).click();
  const upRequest = await moveUpRequest;

  expect(upRequest.postDataJSON()).toEqual({ order: [2, 3, 1] });
  await expectOrderedItems(page, ["Lemons", "Rye bread", "Oat milk"]);
  await expect(page.getByRole("button", { name: "Move Lemons up", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Move Oat milk down", exact: true })).toBeDisabled();

  await page.reload();
  await expectOrderedItems(page, ["Lemons", "Rye bread", "Oat milk"]);
});

test("marks bought items, persists bought state, and clears them", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("button", { name: "Clear bought", exact: true })).toHaveCount(0);

  const boughtRequest = page.waitForRequest(
    (request) => request.method() === "PATCH" && new URL(request.url()).pathname === "/api/items/2",
  );
  await page.getByRole("checkbox", { name: "Bought Lemons", exact: true }).check();
  const request = await boughtRequest;

  expect(request.postDataJSON()).toEqual({ bought: true });
  await expect(page.getByText("3 items · 1 bought")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear bought", exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByText("3 items · 1 bought")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Bought Lemons", exact: true })).toBeChecked();

  const clearRequest = page.waitForRequest(
    (request) => request.method() === "POST" && new URL(request.url()).pathname === "/api/items/clear-bought",
  );
  await page.getByRole("button", { name: "Clear bought", exact: true }).click();
  await clearRequest;

  await expect(page.getByText("2 items · 0 bought")).toBeVisible();
  await expectOrderedItems(page, ["Oat milk", "Rye bread"]);
  await expect(page.getByRole("checkbox", { name: "Bought Lemons", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Clear bought", exact: true })).toHaveCount(0);
});

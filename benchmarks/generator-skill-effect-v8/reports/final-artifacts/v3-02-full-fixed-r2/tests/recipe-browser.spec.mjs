import { expect, test } from "@playwright/test";

const recipeNames = [
  "Lentil soup",
  "Chickpea curry",
  "Herb omelette",
  "Mushroom lasagne",
];

const recipeCard = (page, name) =>
  page.getByRole("article").filter({
    has: page.getByRole("heading", { name }),
  });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recipes", exact: true })).toBeVisible();
});

test("shows all recipe cards", async ({ page }) => {
  await expect(page.getByRole("article")).toHaveCount(4);

  for (const name of recipeNames) {
    await expect(recipeCard(page, name)).toBeVisible();
  }
});

test("updates servings and plan totals from card controls", async ({ page }) => {
  const soup = recipeCard(page, "Lentil soup");
  const curry = recipeCard(page, "Chickpea curry");

  await soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await expect(soup).toContainText("1 serving");

  const addSoupRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/soup") &&
      request.postDataJSON().planned === true,
  );
  await soup.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await addSoupRequest;
  await expect(page.getByText("Plan: 1 recipe · 1 servings")).toBeVisible();

  const addCurryRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/curry") &&
      request.postDataJSON().planned === true,
  );
  await curry.getByRole("button", { name: "Add Chickpea curry to plan" }).click();
  await addCurryRequest;
  await expect(page.getByText("Plan: 2 recipes · 3 servings")).toBeVisible();

  const curryServingsRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/curry") &&
      request.postDataJSON().servings === 3,
  );
  await curry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await curryServingsRequest;
  await expect(page.getByText("Plan: 2 recipes · 4 servings")).toBeVisible();
});

test("filters recipes by one active tag and clears the active tag on a second click", async ({ page }) => {
  await page.getByRole("button", { name: "vegan", exact: true }).click();

  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(recipeCard(page, "Lentil soup")).toBeVisible();
  await expect(recipeCard(page, "Chickpea curry")).toBeVisible();

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(recipeCard(page, "Lentil soup")).toBeVisible();
  await expect(recipeCard(page, "Herb omelette")).toBeVisible();

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("article")).toHaveCount(4);
});

test("keeps planned recipes and servings after reload", async ({ page }) => {
  const lasagne = recipeCard(page, "Mushroom lasagne");

  const addLasagneRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/lasagne") &&
      request.postDataJSON().planned === true,
  );
  await lasagne.getByRole("button", { name: "Add Mushroom lasagne to plan" }).click();
  await addLasagneRequest;

  const lasagneServingsRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/lasagne") &&
      request.postDataJSON().servings === 3,
  );
  await lasagne.getByRole("button", { name: "More servings for Mushroom lasagne" }).click();
  await lasagneServingsRequest;
  await expect(page.getByText("Plan: 1 recipe · 3 servings")).toBeVisible();

  await page.reload();

  const reloadedLasagne = recipeCard(page, "Mushroom lasagne");
  await expect(page.getByText("Plan: 1 recipe · 3 servings")).toBeVisible();
  await expect(reloadedLasagne).toContainText("3 servings");
  await expect(reloadedLasagne.getByRole("button", { name: "Remove Mushroom lasagne from plan" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

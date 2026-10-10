import { expect, test } from "@playwright/test";

const recipes = ["Lentil soup", "Chickpea curry", "Herb omelette", "Mushroom lasagne"];

const recipeCard = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name }) });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recipes", exact: true })).toBeVisible();
});

test("shows the recipe cards and keeps servings above zero", async ({ page }) => {
  await expect(page.getByRole("article")).toHaveCount(4);
  for (const name of recipes) {
    await expect(recipeCard(page, name)).toBeVisible();
  }

  const soup = recipeCard(page, "Lentil soup");
  await soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await expect(soup).toContainText("1 serving");

  await soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await expect(soup).toContainText("1 serving");
});

test("updates the plan totals when recipes and servings change and persists them", async ({ page }) => {
  const soup = recipeCard(page, "Lentil soup");
  const curry = recipeCard(page, "Chickpea curry");
  const planLine = page.getByText(/^Plan:/);

  const soupServingsRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/soup") &&
      request.postDataJSON().servings === 3,
  );
  await soup.getByRole("button", { name: "More servings for Lentil soup" }).click();
  await soupServingsRequest;

  const addSoupRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/soup") &&
      request.postDataJSON().planned === true,
  );
  await soup.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await addSoupRequest;
  await expect(planLine).toHaveText("Plan: 1 recipe · 3 servings");

  const addCurryRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/curry") &&
      request.postDataJSON().planned === true,
  );
  await curry.getByRole("button", { name: "Add Chickpea curry to plan" }).click();
  await addCurryRequest;
  await expect(planLine).toHaveText("Plan: 2 recipes · 5 servings");

  const curryServingsRequest = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/curry") &&
      request.postDataJSON().servings === 3,
  );
  await curry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await curryServingsRequest;
  await expect(planLine).toHaveText("Plan: 2 recipes · 6 servings");

  await page.reload();
  await expect(planLine).toHaveText("Plan: 2 recipes · 6 servings");
  await expect(recipeCard(page, "Lentil soup")).toContainText("3 servings");
  await expect(recipeCard(page, "Chickpea curry")).toContainText("3 servings");
  await expect(
    recipeCard(page, "Lentil soup").getByRole("button", { name: "Remove Lentil soup from plan" }),
  ).toBeVisible();
  await expect(
    recipeCard(page, "Chickpea curry").getByRole("button", { name: "Remove Chickpea curry from plan" }),
  ).toBeVisible();
});

test("filters recipes to one active tag and clears the filter on a second click", async ({ page }) => {
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

  await page.getByRole("button", { name: "bake", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(1);
  await expect(recipeCard(page, "Mushroom lasagne")).toBeVisible();

  await page.getByRole("button", { name: "bake", exact: true }).click();
  await expect(page.getByRole("button", { name: "bake", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("article")).toHaveCount(4);
});

import { expect, test } from "@playwright/test";

const recipes = ["Lentil soup", "Chickpea curry", "Herb omelette", "Mushroom lasagne"];

const recipeCard = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name }) });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recipes", exact: true })).toBeVisible();
});

test("shows every recipe card with its serving controls", async ({ page }) => {
  await expect(page.getByRole("article")).toHaveCount(4);

  for (const recipe of recipes) {
    const card = recipeCard(page, recipe);
    await expect(card).toBeVisible();
    await expect(card.getByText("2 servings")).toBeVisible();
    await expect(card.getByRole("button", { name: `Fewer servings for ${recipe}` })).toBeVisible();
    await expect(card.getByRole("button", { name: `More servings for ${recipe}` })).toBeVisible();
    await expect(card.getByRole("button", { name: `Add ${recipe} to plan` })).toBeVisible();
  }
});

test("keeps the serving stepper from going below one", async ({ page }) => {
  const soup = recipeCard(page, "Lentil soup");

  const firstUpdate = page.waitForRequest((request) => {
    return request.method() === "PATCH" && request.url().endsWith("/api/plan/soup");
  });
  await soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await firstUpdate;

  const floorUpdate = page.waitForRequest((request) => {
    return request.method() === "PATCH" && request.url().endsWith("/api/plan/soup");
  });
  await soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await floorUpdate;

  await expect(soup.getByText("1 serving")).toBeVisible();
});

test("updates plan totals as recipes and servings change and survives reload", async ({ page }) => {
  const soup = recipeCard(page, "Lentil soup");
  const omelette = recipeCard(page, "Herb omelette");
  const planLine = page.getByText(/^Plan:/);

  const soupToggle = page.waitForRequest((request) => {
    return request.method() === "PATCH" && request.url().endsWith("/api/plan/soup");
  });
  await soup.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await soupToggle;
  await expect(planLine).toHaveText("Plan: 1 recipe · 2 servings");

  for (let index = 0; index < 2; index += 1) {
    const servingUpdate = page.waitForRequest((request) => {
      return request.method() === "PATCH" && request.url().endsWith("/api/plan/soup");
    });
    await soup.getByRole("button", { name: "More servings for Lentil soup" }).click();
    await servingUpdate;
  }

  const omeletteToggle = page.waitForRequest((request) => {
    return request.method() === "PATCH" && request.url().endsWith("/api/plan/omelette");
  });
  await omelette.getByRole("button", { name: "Add Herb omelette to plan" }).click();
  await omeletteToggle;

  await expect(planLine).toHaveText("Plan: 2 recipes · 6 servings");

  await page.reload();
  await expect(recipeCard(page, "Lentil soup").getByText("4 servings")).toBeVisible();
  await expect(recipeCard(page, "Lentil soup").getByRole("button", { name: "Remove Lentil soup from plan" })).toBeVisible();
  await expect(recipeCard(page, "Herb omelette").getByRole("button", { name: "Remove Herb omelette from plan" })).toBeVisible();
  await expect(planLine).toHaveText("Plan: 2 recipes · 6 servings");
});

test("filters recipe cards by one active tag and clears the filter on a second click", async ({ page }) => {
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

test("shows the no-match message when the active tag has no recipes", async ({ page }) => {
  await page.evaluate(() => {
    tag = "missing";
    render();
  });

  await expect(page.getByRole("article")).toHaveCount(0);
  await expect(page.getByText("No recipes match")).toBeVisible();
});

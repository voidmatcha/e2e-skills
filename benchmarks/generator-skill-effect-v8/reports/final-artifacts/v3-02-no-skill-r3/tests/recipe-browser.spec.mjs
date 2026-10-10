import { expect, test } from "@playwright/test";

const recipes = ["Lentil soup", "Chickpea curry", "Herb omelette", "Mushroom lasagne"];

const recipeCard = (page, name) =>
  page.locator("article").filter({ has: page.getByRole("heading", { name }) });

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows all recipes and keeps serving counts above zero", async ({ page }) => {
  await page.goto("/");

  for (const recipe of recipes) {
    await expect(recipeCard(page, recipe)).toBeVisible();
  }

  const soup = recipeCard(page, "Lentil soup");
  await expect(soup.getByText("2 servings")).toBeVisible();

  await page.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await expect(soup.getByText("1 serving")).toBeVisible();

  await page.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await expect(soup.getByText("1 serving")).toBeVisible();

  await page.getByRole("button", { name: "More servings for Lentil soup" }).click();
  await expect(soup.getByText("2 servings")).toBeVisible();
});

test("updates the plan total and keeps it after reload", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Plan: 0 recipes · 0 servings")).toBeVisible();

  await page.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await expect(page.getByText("Plan: 1 recipe · 2 servings")).toBeVisible();

  await page.getByRole("button", { name: "Add Chickpea curry to plan" }).click();
  await expect(page.getByText("Plan: 2 recipes · 4 servings")).toBeVisible();

  await page.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await page.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await expect(page.getByText("Plan: 2 recipes · 6 servings")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Plan: 2 recipes · 6 servings")).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Lentil soup from plan" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(recipeCard(page, "Chickpea curry").getByText("4 servings")).toBeVisible();

  await page.getByRole("button", { name: "Remove Lentil soup from plan" }).click();
  await expect(page.getByText("Plan: 1 recipe · 4 servings")).toBeVisible();
});

test("filters recipes by one tag at a time and clears the active chip on second click", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "vegan" }).click();
  await expect(page.getByRole("button", { name: "vegan" })).toHaveAttribute("aria-pressed", "true");
  await expect(recipeCard(page, "Lentil soup")).toBeVisible();
  await expect(recipeCard(page, "Chickpea curry")).toBeVisible();
  await expect(recipeCard(page, "Herb omelette")).toBeHidden();
  await expect(recipeCard(page, "Mushroom lasagne")).toBeHidden();

  await page.getByRole("button", { name: "quick" }).click();
  await expect(page.getByRole("button", { name: "vegan" })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: "quick" })).toHaveAttribute("aria-pressed", "true");
  await expect(recipeCard(page, "Lentil soup")).toBeVisible();
  await expect(recipeCard(page, "Chickpea curry")).toBeHidden();
  await expect(recipeCard(page, "Herb omelette")).toBeVisible();
  await expect(recipeCard(page, "Mushroom lasagne")).toBeHidden();

  await page.getByRole("button", { name: "quick" }).click();
  await expect(page.getByRole("button", { name: "quick" })).toHaveAttribute("aria-pressed", "false");
  for (const recipe of recipes) {
    await expect(recipeCard(page, recipe)).toBeVisible();
  }
});

test("shows the empty state when the active tag has no matching recipes", async ({ page }) => {
  await page.goto("/");

  await page.evaluate(() => {
    eval('tag = "dessert"; render();');
  });

  await expect(page.getByText("No recipes match")).toBeVisible();
  await expect(page.locator("article")).toHaveCount(0);
});

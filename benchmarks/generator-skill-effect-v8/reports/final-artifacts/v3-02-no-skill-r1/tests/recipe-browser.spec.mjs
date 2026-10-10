import { expect, test } from "@playwright/test";

const recipes = ["Lentil soup", "Chickpea curry", "Herb omelette", "Mushroom lasagne"];

const recipeCard = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name }) });

const expectVisibleRecipes = async (page, visibleNames) => {
  for (const name of recipes) {
    await expect(recipeCard(page, name)).toBeVisible({ visible: visibleNames.includes(name) });
  }
};

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows the recipe cards with serving steppers and plan toggles", async ({ page }) => {
  await page.goto("/");

  for (const name of recipes) {
    const card = recipeCard(page, name);
    await expect(card).toBeVisible();
    await expect(card.getByText("2 servings")).toBeVisible();
    await expect(card.getByRole("button", { name: `Fewer servings for ${name}` })).toBeVisible();
    await expect(card.getByRole("button", { name: `More servings for ${name}` })).toBeVisible();
    await expect(card.getByRole("button", { name: `Add ${name} to plan` })).toHaveAttribute("aria-pressed", "false");
  }

  await expect(page.locator("#rc-plan")).toHaveText("Plan: 0 recipes · 0 servings");
});

test("keeps servings at one or more and updates the plan total", async ({ page }) => {
  await page.goto("/");

  const soup = recipeCard(page, "Lentil soup");
  await soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await expect(soup.getByText("1 serving")).toBeVisible();
  await soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await expect(soup.getByText("1 serving")).toBeVisible();

  await soup.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 1 recipe · 1 servings");

  const curry = recipeCard(page, "Chickpea curry");
  await curry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await curry.getByRole("button", { name: "Add Chickpea curry to plan" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 2 recipes · 4 servings");

  await curry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 2 recipes · 5 servings");

  await soup.getByRole("button", { name: "Remove Lentil soup from plan" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 1 recipe · 4 servings");
});

test("filters recipe cards by one active tag and clears the filter on a second click", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "vegan" }).click();
  await expect(page.getByRole("button", { name: "vegan" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "quick" })).toHaveAttribute("aria-pressed", "false");
  await expectVisibleRecipes(page, ["Lentil soup", "Chickpea curry"]);
  await expect(page.getByText("No recipes match")).toBeHidden();

  await page.getByRole("button", { name: "quick" }).click();
  await expect(page.getByRole("button", { name: "vegan" })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: "quick" })).toHaveAttribute("aria-pressed", "true");
  await expectVisibleRecipes(page, ["Lentil soup", "Herb omelette"]);

  await page.getByRole("button", { name: "quick" }).click();
  await expect(page.getByRole("button", { name: "quick" })).toHaveAttribute("aria-pressed", "false");
  await expectVisibleRecipes(page, recipes);
});

test("shows an empty state when an active tag has no matching recipes", async ({ page }) => {
  await page.addInitScript(() => {
    const NativeSet = Set;
    window.Set = class SetWithEmptyRecipeTag extends NativeSet {
      constructor(iterable) {
        super(iterable);
        if (Array.isArray(iterable) && iterable.includes("vegan") && iterable.includes("quick") && iterable.includes("bake")) {
          this.add("dessert");
        }
      }
    };
  });

  await page.goto("/");

  await page.getByRole("button", { name: "dessert" }).click();
  await expect(page.getByText("No recipes match")).toBeVisible();
  await expectVisibleRecipes(page, []);

  await page.getByRole("button", { name: "dessert" }).click();
  await expect(page.getByText("No recipes match")).toBeHidden();
  await expectVisibleRecipes(page, recipes);
});

test("persists planned recipes and servings after a reload", async ({ page }) => {
  await page.goto("/");

  const lasagne = recipeCard(page, "Mushroom lasagne");
  await lasagne.getByRole("button", { name: "More servings for Mushroom lasagne" }).click();
  await lasagne.getByRole("button", { name: "More servings for Mushroom lasagne" }).click();
  await lasagne.getByRole("button", { name: "Add Mushroom lasagne to plan" }).click();

  const omelette = recipeCard(page, "Herb omelette");
  await omelette.getByRole("button", { name: "Fewer servings for Herb omelette" }).click();
  await omelette.getByRole("button", { name: "Add Herb omelette to plan" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 2 recipes · 5 servings");

  await page.reload();

  await expect(recipeCard(page, "Mushroom lasagne").getByText("4 servings")).toBeVisible();
  await expect(recipeCard(page, "Mushroom lasagne").getByRole("button", { name: "Remove Mushroom lasagne from plan" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(recipeCard(page, "Herb omelette").getByText("1 serving")).toBeVisible();
  await expect(recipeCard(page, "Herb omelette").getByRole("button", { name: "Remove Herb omelette from plan" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 2 recipes · 5 servings");
});

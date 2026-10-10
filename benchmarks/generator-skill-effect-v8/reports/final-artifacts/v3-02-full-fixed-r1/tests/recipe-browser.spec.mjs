import { expect, test } from "@playwright/test";

const recipes = ["Lentil soup", "Chickpea curry", "Herb omelette", "Mushroom lasagne"];

const recipeCard = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name }) });

const planLine = (page) => page.getByText(/^Plan: \d+ recipes? . \d+ servings$/);

const resetPlan = async (page) => {
  const response = await page.request.post("/api/reset");
  expect(response.ok()).toBe(true);
};

const expectRecipes = async (page, visibleRecipes) => {
  await expect(page.getByRole("article")).toHaveCount(visibleRecipes.length);
  for (const name of visibleRecipes) {
    await expect(recipeCard(page, name)).toBeVisible();
  }
  for (const name of recipes.filter((recipe) => !visibleRecipes.includes(recipe))) {
    await expect(recipeCard(page, name)).toHaveCount(0);
  }
};

const patchPlan = async (page, action, expectedBody) => {
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/plan/") && response.request().method() === "PATCH",
  );
  await action();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  expect(response.request().postDataJSON()).toEqual(expectedBody);
};

test.beforeEach(async ({ page }) => {
  await resetPlan(page);
});

test("shows all recipe cards with their default servings", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Recipes", exact: true })).toBeVisible();
  await expectRecipes(page, recipes);
  await expect(planLine(page)).toHaveText("Plan: 0 recipes · 0 servings");

  for (const name of recipes) {
    await expect(recipeCard(page, name).getByText("2 servings")).toBeVisible();
    await expect(page.getByRole("button", { name: `Add ${name} to plan`, exact: true })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  }
});

test("keeps servings above zero and updates planned totals after every change", async ({ page }) => {
  await page.goto("/");

  const soup = recipeCard(page, "Lentil soup");
  const curry = recipeCard(page, "Chickpea curry");

  await patchPlan(
    page,
    () => soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click(),
    { servings: 1 },
  );
  await expect(soup.getByText("1 serving")).toBeVisible();

  await patchPlan(
    page,
    () => soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click(),
    { servings: 1 },
  );
  await expect(soup.getByText("1 serving")).toBeVisible();

  await patchPlan(
    page,
    () => page.getByRole("button", { name: "Add Lentil soup to plan", exact: true }).click(),
    { planned: true },
  );
  await expect(planLine(page)).toHaveText("Plan: 1 recipe · 1 servings");

  await patchPlan(
    page,
    () => page.getByRole("button", { name: "Add Chickpea curry to plan", exact: true }).click(),
    { planned: true },
  );
  await expect(planLine(page)).toHaveText("Plan: 2 recipes · 3 servings");

  await patchPlan(
    page,
    () => curry.getByRole("button", { name: "More servings for Chickpea curry" }).click(),
    { servings: 3 },
  );
  await expect(planLine(page)).toHaveText("Plan: 2 recipes · 4 servings");

  await patchPlan(
    page,
    () => page.getByRole("button", { name: "Remove Lentil soup from plan", exact: true }).click(),
    { planned: false },
  );
  await expect(planLine(page)).toHaveText("Plan: 1 recipe · 3 servings");
});

test("filters cards by one active tag and clears the filter on a second click", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "vegan", exact: true }).click();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expectRecipes(page, ["Lentil soup", "Chickpea curry"]);

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expectRecipes(page, ["Lentil soup", "Herb omelette"]);

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expectRecipes(page, recipes);
});

test("shows the empty state when an available tag has no matching recipes", async ({ page }) => {
  await page.route("/", async (route) => {
    const response = await route.fetch();
    const body = await response.text();
    await route.fulfill({
      response,
      body: body.replace(
        "const tags = [...new Set(RECIPES.flatMap((r) => r.tags))];",
        'const tags = [...new Set([...RECIPES.flatMap((r) => r.tags), "empty"])];',
      ),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "empty", exact: true }).click();

  await expect(page.getByRole("article")).toHaveCount(0);
  await expect(page.getByText("No recipes match")).toBeVisible();

  await page.getByRole("button", { name: "empty", exact: true }).click();
  await expectRecipes(page, recipes);
});

test("keeps planned recipes and servings after a reload", async ({ page }) => {
  await page.goto("/");

  const soup = recipeCard(page, "Lentil soup");
  const lasagne = recipeCard(page, "Mushroom lasagne");

  await patchPlan(
    page,
    () => soup.getByRole("button", { name: "More servings for Lentil soup" }).click(),
    { servings: 3 },
  );
  await patchPlan(
    page,
    () => lasagne.getByRole("button", { name: "More servings for Mushroom lasagne" }).click(),
    { servings: 3 },
  );
  await patchPlan(
    page,
    () => page.getByRole("button", { name: "Add Lentil soup to plan", exact: true }).click(),
    { planned: true },
  );
  await patchPlan(
    page,
    () => page.getByRole("button", { name: "Add Mushroom lasagne to plan", exact: true }).click(),
    { planned: true },
  );
  await expect(planLine(page)).toHaveText("Plan: 2 recipes · 6 servings");

  await page.reload();

  await expect(planLine(page)).toHaveText("Plan: 2 recipes · 6 servings");
  await expect(recipeCard(page, "Lentil soup").getByText("3 servings")).toBeVisible();
  await expect(recipeCard(page, "Mushroom lasagne").getByText("3 servings")).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Lentil soup from plan", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("button", { name: "Remove Mushroom lasagne from plan", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

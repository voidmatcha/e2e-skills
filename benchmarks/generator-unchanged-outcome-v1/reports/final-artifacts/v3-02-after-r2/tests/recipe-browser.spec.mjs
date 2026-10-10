import { expect, test } from "@playwright/test";

const recipes = [
  "Lentil soup",
  "Chickpea curry",
  "Herb omelette",
  "Mushroom lasagne",
];

const recipeCard = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name, exact: true }) });

const servingsText = (page, name) => recipeCard(page, name).getByText(/^\d+ servings?$/);

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recipes", exact: true })).toBeVisible();
});

test("shows the four recipe cards with default servings and plan controls", async ({ page }) => {
  await expect(page.getByRole("article")).toHaveCount(4);

  for (const recipe of recipes) {
    const card = recipeCard(page, recipe);
    await expect(card).toBeVisible();
    await expect(servingsText(page, recipe)).toHaveText("2 servings");
    await expect(card.getByRole("button", { name: `Add ${recipe} to plan` })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  }

  await expect(page.getByText("Plan: 0 recipes · 0 servings")).toBeVisible();
});

test("updates plan totals as servings and planned recipes change, then restores them after reload", async ({
  page,
}) => {
  const addSoup = page.getByRole("button", { name: "Add Lentil soup to plan", exact: true });
  const soupMore = page.getByRole("button", { name: "More servings for Lentil soup", exact: true });

  const soupPlanRequest = page.waitForRequest((request) => {
    const payload = request.postDataJSON();
    return request.method() === "PATCH" && request.url().endsWith("/api/plan/soup") && payload.planned === true;
  });
  await addSoup.click();
  await soupPlanRequest;
  await expect(page.getByText("Plan: 1 recipe · 2 servings")).toBeVisible();

  for (const servings of [3, 4]) {
    const servingsRequest = page.waitForRequest((request) => {
      const payload = request.postDataJSON();
      return (
        request.method() === "PATCH" &&
        request.url().endsWith("/api/plan/soup") &&
        payload.servings === servings
      );
    });
    await soupMore.click();
    await servingsRequest;
    await expect(page.getByText(`Plan: 1 recipe · ${servings} servings`)).toBeVisible();
  }

  const omelettePlanRequest = page.waitForRequest((request) => {
    const payload = request.postDataJSON();
    return (
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/omelette") &&
      payload.planned === true
    );
  });
  await page.getByRole("button", { name: "Add Herb omelette to plan", exact: true }).click();
  await omelettePlanRequest;
  await expect(page.getByText("Plan: 2 recipes · 6 servings")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Plan: 2 recipes · 6 servings")).toBeVisible();
  await expect(servingsText(page, "Lentil soup")).toHaveText("4 servings");
  await expect(page.getByRole("button", { name: "Remove Lentil soup from plan", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("button", { name: "Remove Herb omelette from plan", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("keeps the servings stepper at one serving", async ({ page }) => {
  const fewer = page.getByRole("button", { name: "Fewer servings for Chickpea curry", exact: true });

  const oneServingRequest = page.waitForRequest((request) => {
    const payload = request.postDataJSON();
    return (
      request.method() === "PATCH" &&
      request.url().endsWith("/api/plan/curry") &&
      payload.servings === 1
    );
  });
  await fewer.click();
  await oneServingRequest;
  await expect(servingsText(page, "Chickpea curry")).toHaveText("1 serving");

  const floorRequest = page.waitForResponse(
    (response) => response.request().method() === "PATCH" && response.url().endsWith("/api/plan/curry"),
  );
  await fewer.click();
  const response = await floorRequest;
  expect(response.status()).toBe(200);
  await expect(servingsText(page, "Chickpea curry")).toHaveText("1 serving");
});

test("filters recipe cards by one active tag and clears the filter on a second click", async ({ page }) => {
  await page.getByRole("button", { name: "vegan", exact: true }).click();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(recipeCard(page, "Lentil soup")).toBeVisible();
  await expect(recipeCard(page, "Chickpea curry")).toBeVisible();
  await expect(recipeCard(page, "Herb omelette")).toHaveCount(0);

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(recipeCard(page, "Lentil soup")).toBeVisible();
  await expect(recipeCard(page, "Herb omelette")).toBeVisible();
  await expect(recipeCard(page, "Chickpea curry")).toHaveCount(0);

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("article")).toHaveCount(4);
});

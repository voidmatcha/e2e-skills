import { expect, test } from "@playwright/test";

const recipes = ["Lentil soup", "Chickpea curry", "Herb omelette", "Mushroom lasagne"];

const recipeCard = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name }) });

const planLine = (page) => page.getByText(/^Plan: /);

async function resetPlan(request) {
  const response = await request.post("/api/reset");
  expect(response.ok()).toBeTruthy();
}

async function openRecipes(page) {
  await page.goto("/");
  await expect(planLine(page)).toHaveText("Plan: 0 recipes · 0 servings");
}

test.beforeEach(async ({ request }) => {
  await resetPlan(request);
});

test("shows all recipe cards and keeps servings at one or more", async ({ page }) => {
  await openRecipes(page);

  for (const recipe of recipes) {
    await expect(recipeCard(page, recipe)).toContainText("2 servings");
  }

  await recipeCard(page, "Lentil soup").getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await recipeCard(page, "Lentil soup").getByRole("button", { name: "Fewer servings for Lentil soup" }).click();

  await expect(recipeCard(page, "Lentil soup")).toContainText("1 serving");
});

test("updates planned recipe and serving totals and preserves them after reload", async ({ page }) => {
  await openRecipes(page);

  await recipeCard(page, "Lentil soup").getByRole("button", { name: "More servings for Lentil soup" }).click();
  await recipeCard(page, "Chickpea curry").getByRole("button", { name: "More servings for Chickpea curry" }).click();

  const soupPlanRequest = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith("/api/plan/soup")) return false;
    return request.postDataJSON().planned === true;
  });
  await recipeCard(page, "Lentil soup").getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await soupPlanRequest;

  const curryPlanRequest = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith("/api/plan/curry")) return false;
    return request.postDataJSON().planned === true;
  });
  await recipeCard(page, "Chickpea curry").getByRole("button", { name: "Add Chickpea curry to plan" }).click();
  await curryPlanRequest;

  await expect(planLine(page)).toHaveText("Plan: 2 recipes · 6 servings");

  await page.reload();

  await expect(planLine(page)).toHaveText("Plan: 2 recipes · 6 servings");
});

test("filters by one tag at a time and clears the active tag on second click", async ({ page }) => {
  await openRecipes(page);

  await page.getByRole("button", { name: "vegan", exact: true }).click();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(page.getByRole("article")).toHaveText([/Lentil soup/, /Chickpea curry/]);

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(page.getByRole("article")).toHaveText([/Lentil soup/, /Herb omelette/]);

  await page.getByRole("button", { name: "quick", exact: true }).click();

  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("article")).toHaveCount(4);
});

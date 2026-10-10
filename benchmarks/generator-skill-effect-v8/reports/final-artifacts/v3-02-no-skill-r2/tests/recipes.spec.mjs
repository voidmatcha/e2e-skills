import { expect, test } from "@playwright/test";

const recipes = ["Lentil soup", "Chickpea curry", "Herb omelette", "Mushroom lasagne"];

test.beforeEach(async ({ request, page }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("shows the recipe cards with serving steppers and plan toggles", async ({ page }) => {
  for (const recipe of recipes) {
    const card = page.locator("article", { has: page.getByRole("heading", { name: recipe }) });

    await expect(card).toBeVisible();
    await expect(card.getByText("2 servings")).toBeVisible();
    await expect(page.getByRole("button", { name: `Fewer servings for ${recipe}` })).toBeVisible();
    await expect(page.getByRole("button", { name: `More servings for ${recipe}` })).toBeVisible();
    await expect(page.getByRole("button", { name: `Add ${recipe} to plan` })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  }

  await expect(page.locator("#rc-plan")).toHaveText("Plan: 0 recipes · 0 servings");
});

test("updates the plan count and servings total as cards change", async ({ page }) => {
  await page.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 1 recipe · 2 servings");

  await page.getByRole("button", { name: "More servings for Lentil soup" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 1 recipe · 3 servings");

  await page.getByRole("button", { name: "Add Mushroom lasagne to plan" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 2 recipes · 5 servings");

  await page.getByRole("button", { name: "More servings for Mushroom lasagne" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 2 recipes · 6 servings");

  await page.getByRole("button", { name: "Remove Lentil soup from plan" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 1 recipe · 3 servings");
});

test("does not allow serving counts below one", async ({ page }) => {
  const soup = page.locator("article", { has: page.getByRole("heading", { name: "Lentil soup" }) });

  await page.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await expect(soup.getByText("1 serving")).toBeVisible();

  await page.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  await expect(soup.getByText("1 serving")).toBeVisible();

  await page.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 1 recipe · 1 servings");
});

test("filters recipes by one active tag and clears the filter when clicked again", async ({ page }) => {
  await page.getByRole("button", { name: "vegan" }).click();
  await expect(page.getByRole("button", { name: "vegan" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "Lentil soup" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Chickpea curry" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Herb omelette" })).toBeHidden();
  await expect(page.getByRole("heading", { name: "Mushroom lasagne" })).toBeHidden();
  await expect(page.getByText("No recipes match")).toBeHidden();

  await page.getByRole("button", { name: "quick" }).click();
  await expect(page.getByRole("button", { name: "vegan" })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: "quick" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "Lentil soup" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Herb omelette" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Chickpea curry" })).toBeHidden();
  await expect(page.getByRole("heading", { name: "Mushroom lasagne" })).toBeHidden();

  await page.getByRole("button", { name: "quick" }).click();
  await expect(page.getByRole("button", { name: "quick" })).toHaveAttribute("aria-pressed", "false");
  for (const recipe of recipes) {
    await expect(page.getByRole("heading", { name: recipe })).toBeVisible();
  }
});

test("shows an empty state when the active tag has no matches", async ({ page }) => {
  await page.evaluate(() => {
    // The seeded recipes only expose chips with matches, so drive the same filter state to cover the empty branch.
    tag = "dessert";
    render();
  });

  await expect(page.locator("article")).toHaveCount(0);
  await expect(page.getByText("No recipes match")).toBeVisible();
});

test("keeps plan membership and servings after reload", async ({ page }) => {
  await page.getByRole("button", { name: "More servings for Lentil soup" }).click();
  await page.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await page.getByRole("button", { name: "Fewer servings for Chickpea curry" }).click();
  await page.getByRole("button", { name: "Add Chickpea curry to plan" }).click();
  await expect(page.locator("#rc-plan")).toHaveText("Plan: 2 recipes · 4 servings");

  await page.reload();

  const soup = page.locator("article", { has: page.getByRole("heading", { name: "Lentil soup" }) });
  const curry = page.locator("article", { has: page.getByRole("heading", { name: "Chickpea curry" }) });

  await expect(page.locator("#rc-plan")).toHaveText("Plan: 2 recipes · 4 servings");
  await expect(soup.getByText("3 servings")).toBeVisible();
  await expect(curry.getByText("1 serving")).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Lentil soup from plan" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("button", { name: "Remove Chickpea curry from plan" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

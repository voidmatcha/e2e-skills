import { expect, test } from "@playwright/test";

const recipeNames = [
  "Lentil soup",
  "Chickpea curry",
  "Herb omelette",
  "Mushroom lasagne",
];

const cardFor = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name, exact: true }) });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recipes", exact: true })).toBeVisible();
});

test("shows every recipe card and prevents servings from dropping below one", async ({ page }) => {
  await expect(page.getByRole("article")).toHaveCount(4);

  for (const name of recipeNames) {
    await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  }

  const soup = cardFor(page, "Lentil soup");

  await page.getByRole("button", { name: "Fewer servings for Lentil soup", exact: true }).click();
  await expect(soup.getByText("1 serving")).toBeVisible();

  await page.getByRole("button", { name: "Fewer servings for Lentil soup", exact: true }).click();
  await expect(soup.getByText("1 serving")).toBeVisible();
});

test("keeps the plan line in sync with planned recipes and servings after reload", async ({ page }) => {
  const soupPatch = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith("/api/plan/soup")) return false;
    return request.postDataJSON().planned === true;
  });
  await page.getByRole("button", { name: "Add Lentil soup to plan", exact: true }).click();
  await soupPatch;
  await expect(page.getByText("Plan: 1 recipe · 2 servings")).toBeVisible();

  const curryPatch = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith("/api/plan/curry")) return false;
    return request.postDataJSON().planned === true;
  });
  await page.getByRole("button", { name: "Add Chickpea curry to plan", exact: true }).click();
  await curryPatch;
  await expect(page.getByText("Plan: 2 recipes · 4 servings")).toBeVisible();

  const soupServingPatch = page.waitForRequest((request) => {
    if (request.method() !== "PATCH" || !request.url().endsWith("/api/plan/soup")) return false;
    return request.postDataJSON().servings === 3;
  });
  await page.getByRole("button", { name: "More servings for Lentil soup", exact: true }).click();
  await soupServingPatch;
  await expect(page.getByText("Plan: 2 recipes · 5 servings")).toBeVisible();

  await page.reload();

  await expect(page.getByText("Plan: 2 recipes · 5 servings")).toBeVisible();
  await expect(cardFor(page, "Lentil soup").getByText("3 servings")).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Lentil soup from plan", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Chickpea curry from plan", exact: true })).toBeVisible();
});

test("filters recipe cards to one active tag and clears the filter on a second click", async ({ page }) => {
  await page.getByRole("button", { name: "vegan", exact: true }).click();

  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(page.getByRole("heading", { name: "Lentil soup", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Chickpea curry", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "vegan", exact: true }).click();

  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("article")).toHaveCount(4);
});

import { expect, test } from "@playwright/test";

const recipes = [
  "Lentil soup",
  "Chickpea curry",
  "Herb omelette",
  "Mushroom lasagne",
];

const heading = (page, name) => page.getByRole("heading", { name, exact: true });
const button = (page, name) => page.getByRole("button", { name, exact: true });
const cardFor = (page, name) => page.getByRole("article").filter({ has: heading(page, name) });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(heading(page, "Recipes")).toBeVisible();
});

test("shows all recipe cards with default controls", async ({ page }) => {
  await expect(page.getByRole("article")).toHaveCount(4);

  for (const name of recipes) {
    const card = cardFor(page, name);

    await expect(card).toContainText("2 servings");
    await expect(button(page, `Fewer servings for ${name}`)).toBeVisible();
    await expect(button(page, `More servings for ${name}`)).toBeVisible();
    await expect(button(page, `Add ${name} to plan`)).toHaveAttribute("aria-pressed", "false");
  }

  await expect(page.getByText("Plan: 0 recipes · 0 servings")).toBeVisible();
});

test("keeps servings above zero and updates the plan line with every planned change", async ({ page }) => {
  const soup = cardFor(page, "Lentil soup");
  const curry = cardFor(page, "Chickpea curry");

  await button(page, "Fewer servings for Lentil soup").click();
  await expect(soup).toContainText("1 serving");
  await button(page, "Fewer servings for Lentil soup").click();
  await expect(soup).toContainText("1 serving");

  const addSoup = page.waitForRequest((request) =>
    request.method() === "PATCH" &&
    request.url().endsWith("/api/plan/soup") &&
    request.postDataJSON().planned === true
  );
  await button(page, "Add Lentil soup to plan").click();
  await addSoup;
  await expect(page.getByText("Plan: 1 recipe · 1 servings")).toBeVisible();

  await button(page, "More servings for Lentil soup").click();
  await expect(page.getByText("Plan: 1 recipe · 2 servings")).toBeVisible();

  await button(page, "More servings for Lentil soup").click();
  await expect(page.getByText("Plan: 1 recipe · 3 servings")).toBeVisible();

  await button(page, "More servings for Lentil soup").click();
  await expect(page.getByText("Plan: 1 recipe · 4 servings")).toBeVisible();

  const addCurry = page.waitForRequest((request) =>
    request.method() === "PATCH" &&
    request.url().endsWith("/api/plan/curry") &&
    request.postDataJSON().planned === true
  );
  await button(page, "Add Chickpea curry to plan").click();
  await addCurry;
  await expect(curry).toContainText("2 servings");
  await expect(page.getByText("Plan: 2 recipes · 6 servings")).toBeVisible();

  await button(page, "Fewer servings for Chickpea curry").click();
  await expect(page.getByText("Plan: 2 recipes · 5 servings")).toBeVisible();
});

test("filters cards to one tag and clears the active chip on a second click", async ({ page }) => {
  await button(page, "vegan").click();
  await expect(button(page, "vegan")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(heading(page, "Lentil soup")).toBeVisible();
  await expect(heading(page, "Chickpea curry")).toBeVisible();

  await button(page, "quick").click();
  await expect(button(page, "vegan")).toHaveAttribute("aria-pressed", "false");
  await expect(button(page, "quick")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(heading(page, "Herb omelette")).toBeVisible();

  await button(page, "quick").click();
  await expect(button(page, "quick")).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("article")).toHaveCount(4);
});

test("persists planned recipes and servings after reload", async ({ page }) => {
  const soup = cardFor(page, "Lentil soup");

  await button(page, "More servings for Lentil soup").click();
  await expect(soup).toContainText("3 servings");

  const addSoup = page.waitForRequest((request) =>
    request.method() === "PATCH" &&
    request.url().endsWith("/api/plan/soup") &&
    request.postDataJSON().planned === true
  );
  await button(page, "Add Lentil soup to plan").click();
  await addSoup;
  await expect(button(page, "Remove Lentil soup from plan")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Plan: 1 recipe · 3 servings")).toBeVisible();

  await page.reload();
  await expect(button(page, "Remove Lentil soup from plan")).toHaveAttribute("aria-pressed", "true");
  await expect(soup).toContainText("3 servings");
  await expect(page.getByText("Plan: 1 recipe · 3 servings")).toBeVisible();
});

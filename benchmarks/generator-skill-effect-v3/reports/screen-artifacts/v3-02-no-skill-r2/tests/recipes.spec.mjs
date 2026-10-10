import { expect, test } from "@playwright/test";

const NAMES = ["Lentil soup", "Chickpea curry", "Herb omelette", "Mushroom lasagne"];

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 2 })).toHaveCount(4);
});

const card = (page, name) => page.locator("article", { has: page.getByRole("heading", { name }) });
const plan = (page) => page.locator("#rc-plan");

test("lists the four recipe cards with an empty plan", async ({ page }) => {
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(NAMES);
  await expect(plan(page)).toHaveText("Plan: 0 recipes · 0 servings");
  await expect(card(page, "Lentil soup")).toContainText("2 servings");
});

test("stepper changes servings and never goes below 1", async ({ page }) => {
  const soup = card(page, "Lentil soup");
  await soup.getByRole("button", { name: "More servings for Lentil soup" }).click();
  await expect(soup).toContainText("3 servings");
  const fewer = soup.getByRole("button", { name: "Fewer servings for Lentil soup" });
  await fewer.click();
  await fewer.click();
  await expect(soup).toContainText("1 serving");
  await fewer.click();
  await expect(soup.locator(".servings")).toHaveText("1 serving");
});

test("plan line follows toggles and servings changes", async ({ page }) => {
  const soup = card(page, "Lentil soup");
  const curry = card(page, "Chickpea curry");

  await soup.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 2 servings");

  await curry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await curry.getByRole("button", { name: "Add Chickpea curry to plan" }).click();
  await expect(plan(page)).toHaveText("Plan: 2 recipes · 5 servings");

  await soup.getByRole("button", { name: "More servings for Lentil soup" }).click();
  await expect(plan(page)).toHaveText("Plan: 2 recipes · 6 servings");

  await soup.getByRole("button", { name: "Remove Lentil soup from plan" }).click();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 3 servings");
});

test("servings of unplanned recipes are not counted", async ({ page }) => {
  await card(page, "Herb omelette").getByRole("button", { name: "More servings for Herb omelette" }).click();
  await expect(card(page, "Herb omelette")).toContainText("3 servings");
  await expect(plan(page)).toHaveText("Plan: 0 recipes · 0 servings");
});

test("tag chips filter to one tag and a second click clears it", async ({ page }) => {
  const heads = page.getByRole("heading", { level: 2 });
  const vegan = page.getByRole("button", { name: "vegan", exact: true });
  const quick = page.getByRole("button", { name: "quick", exact: true });

  await vegan.click();
  await expect(heads).toHaveText(["Lentil soup", "Chickpea curry"]);
  await expect(vegan).toHaveAttribute("aria-pressed", "true");

  await quick.click();
  await expect(heads).toHaveText(["Lentil soup", "Herb omelette"]);
  await expect(vegan).toHaveAttribute("aria-pressed", "false");

  await page.getByRole("button", { name: "bake", exact: true }).click();
  await expect(heads).toHaveText(["Mushroom lasagne"]);

  await page.getByRole("button", { name: "bake", exact: true }).click();
  await expect(heads).toHaveText(NAMES);
  await expect(page.locator("#rc-empty")).toBeHidden();
});

test("filtering keeps the plan line covering hidden planned recipes", async ({ page }) => {
  await card(page, "Mushroom lasagne").getByRole("button", { name: "Add Mushroom lasagne to plan" }).click();
  await page.getByRole("button", { name: "vegan", exact: true }).click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveCount(2);
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 2 servings");
});

test("plan and servings survive a reload", async ({ page }) => {
  const curry = card(page, "Chickpea curry");
  await curry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await curry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await curry.getByRole("button", { name: "Add Chickpea curry to plan" }).click();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 4 servings");

  await page.reload();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 4 servings");
  await expect(card(page, "Chickpea curry")).toContainText("4 servings");
  await expect(card(page, "Chickpea curry").getByRole("button", { name: "Remove Chickpea curry from plan" })).toBeVisible();
  await expect(card(page, "Lentil soup").getByRole("button", { name: "Add Lentil soup to plan" })).toBeVisible();
});

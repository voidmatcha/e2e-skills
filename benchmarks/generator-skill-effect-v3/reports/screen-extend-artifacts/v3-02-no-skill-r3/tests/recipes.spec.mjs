import { expect, test } from "@playwright/test";

const NAMES = ["Lentil soup", "Chickpea curry", "Herb omelette", "Mushroom lasagne"];

const card = (page, name) => page.locator("article", { has: page.getByRole("heading", { name }) });
const plan = (page) => page.locator("#rc-plan");

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Lentil soup" })).toBeVisible();
});

test("lists four recipes with two servings and an empty plan", async ({ page }) => {
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(NAMES);
  for (const name of NAMES) {
    await expect(card(page, name).locator(".servings")).toHaveText("2 servings");
    await expect(card(page, name).getByRole("button", { name: `Add ${name} to plan` })).toBeVisible();
  }
  await expect(plan(page)).toHaveText("Plan: 0 recipes · 0 servings");
});

test("stepper changes servings and never goes below 1", async ({ page }) => {
  const soup = card(page, "Lentil soup");
  await soup.getByRole("button", { name: "More servings for Lentil soup" }).click();
  await expect(soup.locator(".servings")).toHaveText("3 servings");
  const fewer = soup.getByRole("button", { name: "Fewer servings for Lentil soup" });
  await fewer.click();
  await fewer.click();
  await expect(soup.locator(".servings")).toHaveText("1 serving");
  await fewer.click();
  await expect(soup.locator(".servings")).toHaveText("1 serving");
  await expect(card(page, "Chickpea curry").locator(".servings")).toHaveText("2 servings");
});

test("plan line follows toggles and servings changes", async ({ page }) => {
  await card(page, "Lentil soup").getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 2 servings");

  await card(page, "Herb omelette").getByRole("button", { name: "Add Herb omelette to plan" }).click();
  await expect(plan(page)).toHaveText("Plan: 2 recipes · 4 servings");

  await card(page, "Lentil soup").getByRole("button", { name: "More servings for Lentil soup" }).click();
  await expect(plan(page)).toHaveText("Plan: 2 recipes · 5 servings");

  // Servings of unplanned recipes are not counted.
  await card(page, "Mushroom lasagne").getByRole("button", { name: "More servings for Mushroom lasagne" }).click();
  await expect(plan(page)).toHaveText("Plan: 2 recipes · 5 servings");

  await card(page, "Herb omelette").getByRole("button", { name: "Remove Herb omelette from plan" }).click();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 3 servings");
  await expect(card(page, "Herb omelette").getByRole("button", { name: "Add Herb omelette to plan" })).toHaveAttribute("aria-pressed", "false");
});

test("tag chips filter cards one tag at a time", async ({ page }) => {
  const cards = page.getByRole("heading", { level: 2 });
  const chip = (name) => page.locator("#rc-tags").getByRole("button", { name, exact: true });

  await chip("vegan").click();
  await expect(cards).toHaveText(["Lentil soup", "Chickpea curry"]);
  await expect(chip("vegan")).toHaveAttribute("aria-pressed", "true");

  await chip("quick").click();
  await expect(cards).toHaveText(["Lentil soup", "Herb omelette"]);
  await expect(chip("vegan")).toHaveAttribute("aria-pressed", "false");

  await chip("bake").click();
  await expect(cards).toHaveText(["Mushroom lasagne"]);
  await expect(page.locator("#rc-empty")).toBeHidden();
});

test("clicking the active chip clears the filter", async ({ page }) => {
  const chip = page.locator("#rc-tags").getByRole("button", { name: "bake", exact: true });
  await chip.click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveCount(1);
  await chip.click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(NAMES);
  await expect(chip).toHaveAttribute("aria-pressed", "false");
});

test("filtering keeps the plan line covering all recipes", async ({ page }) => {
  await card(page, "Mushroom lasagne").getByRole("button", { name: "Add Mushroom lasagne to plan" }).click();
  await page.locator("#rc-tags").getByRole("button", { name: "vegan", exact: true }).click();
  await expect(card(page, "Mushroom lasagne")).toHaveCount(0);
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 2 servings");
});

test("plan membership and servings survive a reload", async ({ page }) => {
  const curry = card(page, "Chickpea curry");
  await curry.getByRole("button", { name: "Add Chickpea curry to plan" }).click();
  await curry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await curry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 4 servings");

  await page.reload();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 4 servings");
  await expect(card(page, "Chickpea curry").locator(".servings")).toHaveText("4 servings");
  await expect(card(page, "Chickpea curry").getByRole("button", { name: "Remove Chickpea curry from plan" })).toBeVisible();
  await expect(card(page, "Lentil soup").locator(".servings")).toHaveText("2 servings");
});

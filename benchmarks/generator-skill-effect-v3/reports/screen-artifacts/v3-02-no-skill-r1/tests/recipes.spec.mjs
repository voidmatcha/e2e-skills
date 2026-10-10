import { expect, test } from "@playwright/test";

const NAMES = ["Lentil soup", "Chickpea curry", "Herb omelette", "Mushroom lasagne"];

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 2 })).toHaveCount(4);
});

const card = (page, name) => page.locator("article", { has: page.getByRole("heading", { name }) });
const plan = (page) => page.locator("#rc-plan");
const more = (page, name) => page.getByRole("button", { name: `More servings for ${name}` });
const fewer = (page, name) => page.getByRole("button", { name: `Fewer servings for ${name}` });
const toggle = (page, name) => page.getByRole("button", { name: new RegExp(`^(Add|Remove) ${name} (to|from) plan$`) });

test("lists the four recipes with 2 servings and an empty plan", async ({ page }) => {
  for (const name of NAMES) {
    await expect(card(page, name)).toBeVisible();
    await expect(card(page, name).locator(".servings")).toHaveText("2 servings");
    await expect(toggle(page, name)).toHaveText("Add to plan");
  }
  await expect(plan(page)).toHaveText("Plan: 0 recipes · 0 servings");
});

test("stepper changes servings and never goes below 1", async ({ page }) => {
  const servings = card(page, "Lentil soup").locator(".servings");
  await more(page, "Lentil soup").click();
  await expect(servings).toHaveText("3 servings");
  await fewer(page, "Lentil soup").click();
  await fewer(page, "Lentil soup").click();
  await expect(servings).toHaveText("1 serving");
  await fewer(page, "Lentil soup").click();
  await expect(servings).toHaveText("1 serving");
  await more(page, "Lentil soup").click();
  await expect(servings).toHaveText("2 servings");
});

test("plan line counts planned recipes and totals servings", async ({ page }) => {
  await toggle(page, "Lentil soup").click();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 2 servings");
  await toggle(page, "Herb omelette").click();
  await expect(plan(page)).toHaveText("Plan: 2 recipes · 4 servings");
  await more(page, "Lentil soup").click();
  await more(page, "Lentil soup").click();
  await expect(plan(page)).toHaveText("Plan: 2 recipes · 6 servings");
  await fewer(page, "Herb omelette").click();
  await expect(plan(page)).toHaveText("Plan: 2 recipes · 5 servings");
  await toggle(page, "Lentil soup").click();
  await expect(toggle(page, "Lentil soup")).toHaveText("Add to plan");
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 1 servings");
});

test("servings of unplanned recipes are not counted until planned", async ({ page }) => {
  await more(page, "Chickpea curry").click();
  await expect(card(page, "Chickpea curry").locator(".servings")).toHaveText("3 servings");
  await expect(plan(page)).toHaveText("Plan: 0 recipes · 0 servings");
  await toggle(page, "Chickpea curry").click();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 3 servings");
});

test("tag chips filter to one tag at a time", async ({ page }) => {
  const visible = async (names) => {
    for (const name of NAMES) {
      await expect(card(page, name)).toHaveCount(names.includes(name) ? 1 : 0);
    }
  };
  const chip = (t) => page.getByRole("button", { name: t, exact: true });

  await chip("vegan").click();
  await expect(chip("vegan")).toHaveAttribute("aria-pressed", "true");
  await visible(["Lentil soup", "Chickpea curry"]);

  await chip("quick").click();
  await expect(chip("quick")).toHaveAttribute("aria-pressed", "true");
  await expect(chip("vegan")).toHaveAttribute("aria-pressed", "false");
  await visible(["Lentil soup", "Herb omelette"]);

  await chip("bake").click();
  await visible(["Mushroom lasagne"]);
  await expect(page.getByText("No recipes match")).toBeHidden();

  await chip("bake").click();
  await expect(chip("bake")).toHaveAttribute("aria-pressed", "false");
  await visible(NAMES);
});

test("filtering does not change the plan line", async ({ page }) => {
  await toggle(page, "Mushroom lasagne").click();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 2 servings");
  await page.getByRole("button", { name: "vegan", exact: true }).click();
  await expect(card(page, "Mushroom lasagne")).toHaveCount(0);
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 2 servings");
});

test("plan membership and servings survive a reload", async ({ page }) => {
  await toggle(page, "Chickpea curry").click();
  await more(page, "Chickpea curry").click();
  await more(page, "Chickpea curry").click();
  await fewer(page, "Mushroom lasagne").click();
  await expect(card(page, "Mushroom lasagne").locator(".servings")).toHaveText("1 serving");
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 4 servings");

  await page.reload();
  await expect(plan(page)).toHaveText("Plan: 1 recipe · 4 servings");
  await expect(card(page, "Chickpea curry").locator(".servings")).toHaveText("4 servings");
  await expect(toggle(page, "Chickpea curry")).toHaveText("Remove from plan");
  await expect(card(page, "Mushroom lasagne").locator(".servings")).toHaveText("1 serving");
  await expect(toggle(page, "Mushroom lasagne")).toHaveText("Add to plan");
});

import { expect, test } from "@playwright/test";

const cards = (page) => page.getByRole("article");
const card = (page, name) => page.getByRole("article").filter({ has: page.getByRole("heading", { name }) });
const planLine = (page) => page.getByText(/^Plan: \d+ recipes? · \d+ servings$/);

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(cards(page)).toHaveCount(4);
});

test("plan toggle and servings drive the plan line", async ({ page }) => {
  await expect(planLine(page)).toHaveText("Plan: 0 recipes · 0 servings");
  await page.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  await expect(page.getByRole("button", { name: "Remove Lentil soup from plan" })).toHaveAttribute("aria-pressed", "true");
  await expect(planLine(page)).toHaveText("Plan: 1 recipe · 2 servings");
  await page.getByRole("button", { name: "More servings for Lentil soup" }).click();
  await page.getByRole("button", { name: "More servings for Lentil soup" }).click();
  await expect(card(page, "Lentil soup")).toContainText("4 servings");
  await expect(planLine(page)).toHaveText("Plan: 1 recipe · 4 servings");
  await page.getByRole("button", { name: "Add Herb omelette to plan" }).click();
  await expect(planLine(page)).toHaveText("Plan: 2 recipes · 6 servings");
});

test("servings never go below one", async ({ page }) => {
  await page.getByRole("button", { name: "Fewer servings for Chickpea curry" }).click();
  await expect(card(page, "Chickpea curry")).toContainText("1 serving");
  await page.getByRole("button", { name: "Fewer servings for Chickpea curry" }).click();
  await expect(card(page, "Chickpea curry")).toContainText("1 serving");
  await expect(card(page, "Chickpea curry")).not.toContainText("0 serving");
});

test("plan and servings survive a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Add Mushroom lasagne to plan" }).click();
  await page.getByRole("button", { name: "More servings for Mushroom lasagne" }).click();
  await expect(card(page, "Mushroom lasagne")).toContainText("3 servings");
  await page.reload();
  await expect(card(page, "Mushroom lasagne")).toContainText("3 servings");
  await expect(page.getByRole("button", { name: "Remove Mushroom lasagne from plan" })).toBeVisible();
  await expect(planLine(page)).toHaveText("Plan: 1 recipe · 3 servings");
});

test("tag chips filter, show the empty state and clear on a second click", async ({ page }) => {
  await page.getByRole("button", { name: "vegan" }).click();
  await expect(cards(page)).toHaveCount(2);
  await expect(page.getByRole("button", { name: "vegan" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "bake" }).click();
  await expect(cards(page)).toHaveText([/Mushroom lasagne/]);
  await page.getByRole("button", { name: "bake" }).click();
  await expect(cards(page)).toHaveCount(4);
  await expect(page.getByRole("button", { name: "bake" })).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", { name: "quick" }).click();
  await page.getByRole("button", { name: "Add Herb omelette to plan" }).click();
  await expect(cards(page)).toHaveCount(2);
  await expect(page.getByText("No recipes match")).toBeHidden();
});

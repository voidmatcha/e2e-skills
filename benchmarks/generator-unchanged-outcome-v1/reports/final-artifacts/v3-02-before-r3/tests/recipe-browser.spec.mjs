import { expect, test } from "@playwright/test";

const recipeNames = [
  "Lentil soup",
  "Chickpea curry",
  "Herb omelette",
  "Mushroom lasagne",
];

const card = (page, name) =>
  page.getByRole("article").filter({
    has: page.getByRole("heading", { name }),
  });

const planLine = (page) => page.getByText(/^Plan:/);

async function resetPlan(request) {
  const response = await request.post("/api/reset");
  expect(response.ok()).toBe(true);
}

async function expectPlanPatch(page, id, expectedBody, action) {
  const requestPromise = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" &&
      new URL(request.url()).pathname === `/api/plan/${id}`,
  );

  await action();

  const request = await requestPromise;
  expect(request.postDataJSON()).toEqual(expectedBody);
}

test.beforeEach(async ({ page, request }) => {
  await resetPlan(request);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recipes", exact: true })).toBeVisible();
});

test("shows all recipe cards and filters by one active tag at a time", async ({ page }) => {
  await expect(page.getByRole("article")).toHaveCount(4);
  for (const name of recipeNames) {
    await expect(card(page, name)).toBeVisible();
  }

  await page.getByRole("button", { name: "vegan", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(card(page, "Lentil soup")).toBeVisible();
  await expect(card(page, "Chickpea curry")).toBeVisible();
  await expect(card(page, "Herb omelette")).toBeHidden();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(card(page, "Lentil soup")).toBeVisible();
  await expect(card(page, "Herb omelette")).toBeVisible();
  await expect(card(page, "Chickpea curry")).toBeHidden();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(4);
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute("aria-pressed", "false");
});

test("shows an empty message when the active tag has no recipes", async ({ page, request }) => {
  await resetPlan(request);
  await page.route("**/", async (route) => {
    const response = await route.fetch();
    const body = (await response.text()).replace(
      "const tags = [...new Set(RECIPES.flatMap((r) => r.tags))];",
      'const tags = [...new Set(RECIPES.flatMap((r) => r.tags)), "dessert"];',
    );

    await route.fulfill({
      response,
      body,
      headers: {
        ...response.headers(),
        "content-type": "text/html; charset=utf-8",
      },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "dessert", exact: true }).click();

  await expect(page.getByText("No recipes match")).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(0);

  await page.getByRole("button", { name: "dessert", exact: true }).click();
  await expect(page.getByText("No recipes match")).toBeHidden();
  await expect(page.getByRole("article")).toHaveCount(4);
});

test("keeps servings above zero and updates the plan total", async ({ page }) => {
  const lentilSoup = card(page, "Lentil soup");

  await expectPlanPatch(page, "soup", { planned: true }, async () => {
    await lentilSoup.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  });
  await expect(planLine(page)).toHaveText("Plan: 1 recipe · 2 servings");

  await expectPlanPatch(page, "soup", { servings: 3 }, async () => {
    await lentilSoup.getByRole("button", { name: "More servings for Lentil soup" }).click();
  });
  await expect(planLine(page)).toHaveText("Plan: 1 recipe · 3 servings");

  await expectPlanPatch(page, "soup", { servings: 2 }, async () => {
    await lentilSoup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  });
  await expectPlanPatch(page, "soup", { servings: 1 }, async () => {
    await lentilSoup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  });
  await expectPlanPatch(page, "soup", { servings: 1 }, async () => {
    await lentilSoup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click();
  });

  await expect(lentilSoup.getByText("1 serving")).toBeVisible();
  await expect(planLine(page)).toHaveText("Plan: 1 recipe · 1 servings");
});

test("stores planned recipes and servings across a reload", async ({ page }) => {
  const lentilSoup = card(page, "Lentil soup");
  const chickpeaCurry = card(page, "Chickpea curry");

  await expectPlanPatch(page, "soup", { planned: true }, async () => {
    await lentilSoup.getByRole("button", { name: "Add Lentil soup to plan" }).click();
  });
  await expectPlanPatch(page, "curry", { servings: 3 }, async () => {
    await chickpeaCurry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  });
  await expectPlanPatch(page, "curry", { servings: 4 }, async () => {
    await chickpeaCurry.getByRole("button", { name: "More servings for Chickpea curry" }).click();
  });
  await expectPlanPatch(page, "curry", { planned: true }, async () => {
    await chickpeaCurry.getByRole("button", { name: "Add Chickpea curry to plan" }).click();
  });

  await expect(planLine(page)).toHaveText("Plan: 2 recipes · 6 servings");

  await page.reload();

  await expect(planLine(page)).toHaveText("Plan: 2 recipes · 6 servings");
  await expect(card(page, "Lentil soup").getByRole("button", { name: "Remove Lentil soup from plan" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(card(page, "Chickpea curry").getByText("4 servings")).toBeVisible();
  await expect(card(page, "Chickpea curry").getByRole("button", { name: "Remove Chickpea curry from plan" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

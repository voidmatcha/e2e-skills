import { expect, test } from "@playwright/test";

const recipes = [
  "Lentil soup",
  "Chickpea curry",
  "Herb omelette",
  "Mushroom lasagne",
];

const cardFor = (page, name) =>
  page.getByRole("article").filter({
    has: page.getByRole("heading", { name }),
  });

const planLine = (page) => page.getByText(/^Plan:/);

async function resetAndOpen(page) {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recipes" })).toBeVisible();
}

async function expectPlanPatch(page, id, body, action) {
  const patch = page.waitForRequest((request) => {
    if (request.method() !== "PATCH") return false;
    return new URL(request.url()).pathname === `/api/plan/${id}`;
  });

  await action();

  const request = await patch;
  expect(request.postDataJSON()).toEqual(body);
}

test.describe("recipe browser", () => {
  test.beforeEach(async ({ page }) => {
    await resetAndOpen(page);
  });

  test("shows the four recipe cards with their default servings", async ({ page }) => {
    for (const recipe of recipes) {
      const card = cardFor(page, recipe);
      await expect(card).toBeVisible();
      await expect(card.getByText("2 servings")).toBeVisible();
      await expect(
        card.getByRole("button", { name: `Add ${recipe} to plan` }),
      ).toBeVisible();
    }

    await expect(planLine(page)).toHaveText("Plan: 0 recipes · 0 servings");
  });

  test("keeps the plan total in sync with toggles, serving changes, and reloads", async ({
    page,
  }) => {
    await expectPlanPatch(page, "soup", { planned: true }, () =>
      cardFor(page, "Lentil soup")
        .getByRole("button", { name: "Add Lentil soup to plan" })
        .click(),
    );
    await expect(planLine(page)).toHaveText("Plan: 1 recipe · 2 servings");

    await expectPlanPatch(page, "soup", { servings: 3 }, () =>
      cardFor(page, "Lentil soup")
        .getByRole("button", { name: "More servings for Lentil soup" })
        .click(),
    );
    await expect(planLine(page)).toHaveText("Plan: 1 recipe · 3 servings");

    await expectPlanPatch(page, "curry", { servings: 3 }, () =>
      cardFor(page, "Chickpea curry")
        .getByRole("button", { name: "More servings for Chickpea curry" })
        .click(),
    );
    await expectPlanPatch(page, "curry", { planned: true }, () =>
      cardFor(page, "Chickpea curry")
        .getByRole("button", { name: "Add Chickpea curry to plan" })
        .click(),
    );
    await expect(planLine(page)).toHaveText("Plan: 2 recipes · 6 servings");

    await page.reload();
    await expect(
      cardFor(page, "Lentil soup").getByText("3 servings"),
    ).toBeVisible();
    await expect(
      cardFor(page, "Chickpea curry").getByText("3 servings"),
    ).toBeVisible();
    await expect(
      cardFor(page, "Lentil soup").getByRole("button", {
        name: "Remove Lentil soup from plan",
      }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(planLine(page)).toHaveText("Plan: 2 recipes · 6 servings");
  });

  test("does not reduce a recipe below one serving", async ({ page }) => {
    const lentilSoup = cardFor(page, "Lentil soup");

    await expectPlanPatch(page, "soup", { servings: 1 }, () =>
      lentilSoup
        .getByRole("button", { name: "Fewer servings for Lentil soup" })
        .click(),
    );
    await expect(lentilSoup.getByText("1 serving")).toBeVisible();

    await expectPlanPatch(page, "soup", { servings: 1 }, () =>
      lentilSoup
        .getByRole("button", { name: "Fewer servings for Lentil soup" })
        .click(),
    );
    await expect(lentilSoup.getByText("1 serving")).toBeVisible();
  });

  test("filters cards to one active tag and clears the filter on a second click", async ({
    page,
  }) => {
    await expect(cardFor(page, "Lentil soup")).toBeVisible();
    await expect(cardFor(page, "Chickpea curry")).toBeVisible();
    await expect(cardFor(page, "Herb omelette")).toBeVisible();
    await expect(cardFor(page, "Mushroom lasagne")).toBeVisible();

    await page.getByRole("button", { name: "vegan" }).click();

    await expect(page.getByRole("button", { name: "vegan" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(cardFor(page, "Lentil soup")).toBeVisible();
    await expect(cardFor(page, "Chickpea curry")).toBeVisible();
    await expect(cardFor(page, "Herb omelette")).toHaveCount(0);
    await expect(cardFor(page, "Mushroom lasagne")).toHaveCount(0);

    await page.getByRole("button", { name: "quick" }).click();
    await expect(page.getByRole("button", { name: "quick" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByRole("button", { name: "vegan" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await expect(cardFor(page, "Lentil soup")).toBeVisible();
    await expect(cardFor(page, "Herb omelette")).toBeVisible();
    await expect(cardFor(page, "Chickpea curry")).toHaveCount(0);

    await page.getByRole("button", { name: "quick" }).click();
    await expect(page.getByRole("article")).toHaveCount(4);
    await expect(page.getByRole("button", { name: "quick" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  test("shows the empty state when the selected tag has no matching recipes", async ({
    page,
  }) => {
    // JUSTIFIED: The current UI only renders chips for tags that have recipes; this reaches the app's empty-state branch without changing production code.
    await page.evaluate(() => {
      tag = "dessert";
      render();
    });

    await expect(page.getByText("No recipes match")).toBeVisible();
    await expect(page.getByRole("article")).toHaveCount(0);
  });
});

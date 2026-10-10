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

const patchPlan = async (page, action) => {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/plan/") &&
      response.request().method() === "PATCH" &&
      response.status() === 200,
  );
  await action();
  return responsePromise;
};

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("Plan: 0 recipes · 0 servings")).toBeVisible();
});

test("keeps serving steppers above zero and updates planned serving totals", async ({
  page,
}) => {
  const soup = cardFor(page, "Lentil soup");

  await patchPlan(page, () =>
    soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click(),
  );
  await patchPlan(page, () =>
    soup.getByRole("button", { name: "Fewer servings for Lentil soup" }).click(),
  );
  await expect(soup.getByText("1 serving")).toBeVisible();

  await patchPlan(page, () =>
    soup.getByRole("button", { name: "Add Lentil soup to plan" }).click(),
  );
  await expect(page.getByText("Plan: 1 recipe · 1 servings")).toBeVisible();

  await patchPlan(page, () =>
    soup.getByRole("button", { name: "More servings for Lentil soup" }).click(),
  );
  await patchPlan(page, () =>
    soup.getByRole("button", { name: "More servings for Lentil soup" }).click(),
  );
  await expect(page.getByText("Plan: 1 recipe · 3 servings")).toBeVisible();
});

test("stores planned recipes and servings across a reload", async ({ page }) => {
  const soup = cardFor(page, "Lentil soup");
  const curry = cardFor(page, "Chickpea curry");

  await patchPlan(page, () =>
    soup.getByRole("button", { name: "Add Lentil soup to plan" }).click(),
  );
  await patchPlan(page, () =>
    curry.getByRole("button", { name: "Add Chickpea curry to plan" }).click(),
  );
  await patchPlan(page, () =>
    curry.getByRole("button", { name: "More servings for Chickpea curry" }).click(),
  );
  await patchPlan(page, () =>
    curry.getByRole("button", { name: "More servings for Chickpea curry" }).click(),
  );

  await expect(page.getByText("Plan: 2 recipes · 6 servings")).toBeVisible();

  await page.reload();

  await expect(page.getByText("Plan: 2 recipes · 6 servings")).toBeVisible();
  await expect(cardFor(page, "Lentil soup").getByText("2 servings")).toBeVisible();
  await expect(cardFor(page, "Chickpea curry").getByText("4 servings")).toBeVisible();
  await expect(
    cardFor(page, "Lentil soup").getByRole("button", {
      name: "Remove Lentil soup from plan",
    }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    cardFor(page, "Chickpea curry").getByRole("button", {
      name: "Remove Chickpea curry from plan",
    }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("filters recipes by one active tag and clears the filter on a second click", async ({
  page,
}) => {
  await expect(page.getByRole("article")).toHaveCount(recipes.length);

  await page.getByRole("button", { name: "vegan", exact: true }).click();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(cardFor(page, "Lentil soup")).toBeVisible();
  await expect(cardFor(page, "Chickpea curry")).toBeVisible();

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("button", { name: "vegan", exact: true })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(cardFor(page, "Lentil soup")).toBeVisible();
  await expect(cardFor(page, "Herb omelette")).toBeVisible();

  await page.getByRole("button", { name: "quick", exact: true }).click();
  await expect(page.getByRole("button", { name: "quick", exact: true })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await expect(page.getByRole("article")).toHaveCount(recipes.length);
});

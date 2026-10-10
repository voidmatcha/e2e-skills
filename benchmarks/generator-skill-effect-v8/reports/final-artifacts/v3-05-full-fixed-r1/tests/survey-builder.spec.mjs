import { expect, test } from "@playwright/test";

const questionCard = (page, text) =>
  page.locator("article").filter({ has: page.getByRole("heading", { name: new RegExp(`^Q\\d+: ${text}$`) }) });

test.beforeEach(async ({ request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.status()).toBe(200);
});

test("adds and removes options for only the targeted question", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("2 questions · 5 options")).toBeVisible();

  const heardQuestion = questionCard(page, "How did you hear about us\\?");
  const featuresQuestion = questionCard(page, "Which features do you use\\?");

  await heardQuestion.getByLabel("New option for How did you hear about us?").fill("Podcast");
  const addResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/questions/1/options") &&
      response.request().method() === "POST",
  );
  await heardQuestion
    .getByRole("button", { name: "Add option to How did you hear about us?", exact: true })
    .click();
  const added = await addResponse;
  expect(added.status()).toBe(200);
  expect(added.request().postDataJSON()).toEqual({ text: "Podcast" });

  await expect(page.getByText("2 questions · 6 options")).toBeVisible();
  await expect(heardQuestion.getByText("Podcast", { exact: true })).toBeVisible();
  await expect(featuresQuestion.getByRole("listitem")).toHaveCount(2);

  await expect(heardQuestion.getByText("Search", { exact: true })).toBeVisible();
  const removeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/questions/1/options/1") &&
      response.request().method() === "DELETE",
  );
  await heardQuestion
    .getByRole("button", { name: "Remove option Search from How did you hear about us?", exact: true })
    .click();
  const removed = await removeResponse;
  expect(removed.status()).toBe(200);

  await expect(page.getByText("2 questions · 5 options")).toBeVisible();
  await expect(heardQuestion.getByText("Friend", { exact: true })).toBeVisible();
  await expect(heardQuestion.getByText("Advert", { exact: true })).toBeVisible();
  await expect(heardQuestion.getByRole("list")).not.toContainText("Search");
  await expect(featuresQuestion.getByText("Export", { exact: true })).toBeVisible();
  await expect(featuresQuestion.getByText("Sharing", { exact: true })).toBeVisible();

  await page.reload();

  const reloadedHeardQuestion = questionCard(page, "How did you hear about us\\?");
  const reloadedFeaturesQuestion = questionCard(page, "Which features do you use\\?");
  await expect(page.getByText("2 questions · 5 options")).toBeVisible();
  await expect(reloadedHeardQuestion.getByText("Podcast", { exact: true })).toBeVisible();
  await expect(reloadedHeardQuestion.getByRole("list")).not.toContainText("Search");
  await expect(reloadedFeaturesQuestion.getByRole("listitem")).toHaveCount(2);
});

test("reorders questions and previews the current survey", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Q1: How did you hear about us?", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Q2: Which features do you use?", exact: true })).toBeVisible();

  const moveDownResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/order") && response.request().method() === "PUT",
  );
  await page.getByRole("button", { name: "Move question down: How did you hear about us?", exact: true }).click();
  const movedDown = await moveDownResponse;
  expect(movedDown.status()).toBe(200);
  expect(movedDown.request().postDataJSON()).toEqual({ order: [2, 1] });

  await expect(page.getByRole("heading", { name: "Q1: Which features do you use?", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Q2: How did you hear about us?", exact: true })).toBeVisible();

  const moveUpResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/order") && response.request().method() === "PUT",
  );
  await page.getByRole("button", { name: "Move question up: How did you hear about us?", exact: true }).click();
  const movedUp = await moveUpResponse;
  expect(movedUp.status()).toBe(200);
  expect(movedUp.request().postDataJSON()).toEqual({ order: [1, 2] });

  const finalMoveUpResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/order") && response.request().method() === "PUT",
  );
  await page.getByRole("button", { name: "Move question up: Which features do you use?", exact: true }).click();
  const finalOrder = await finalMoveUpResponse;
  expect(finalOrder.status()).toBe(200);
  expect(finalOrder.request().postDataJSON()).toEqual({ order: [2, 1] });

  await page.getByRole("button", { name: "Preview", exact: true }).click();

  await expect(page.getByRole("button", { name: "Hide preview", exact: true })).toBeVisible();
  const preview = page.getByRole("region", { name: "Preview", exact: true });
  await expect(preview).toBeVisible();

  const featuresPreview = preview.getByRole("group", { name: "1. Which features do you use?" });
  await expect(featuresPreview.getByRole("checkbox", { name: "Export" })).toBeVisible();
  await expect(featuresPreview.getByRole("checkbox", { name: "Sharing" })).toBeVisible();
  await expect(featuresPreview.getByRole("checkbox")).toHaveCount(2);

  const heardPreview = preview.getByRole("group", { name: "2. How did you hear about us?" });
  await expect(heardPreview.getByRole("radio", { name: "Friend" })).toBeVisible();
  await expect(heardPreview.getByRole("radio", { name: "Search" })).toBeVisible();
  await expect(heardPreview.getByRole("radio", { name: "Advert" })).toBeVisible();
  await expect(heardPreview.getByRole("radio")).toHaveCount(3);

  await page.reload();

  await expect(page.getByRole("heading", { name: "Q1: Which features do you use?", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Q2: How did you hear about us?", exact: true })).toBeVisible();
});

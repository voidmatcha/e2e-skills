import { expect, test } from "@playwright/test";

const HEAR_QUESTION = "How did you hear about us?";
const FEATURES_QUESTION = "Which features do you use?";

function optionList(page, question) {
  return page.getByRole("list", { name: `Options for ${question}`, exact: true });
}

function optionItems(page, question) {
  return optionList(page, question).getByRole("listitem");
}

function questionHeadings(page) {
  return page.getByRole("main").getByRole("heading", { level: 2 });
}

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("2 questions · 5 options")).toBeVisible();
});

test("adds and removes options only on the selected question", async ({ page }) => {
  await optionList(page, HEAR_QUESTION)
    .getByRole("button", { name: `Remove option Friend from ${HEAR_QUESTION}`, exact: true })
    .waitFor();

  await page.getByLabel(`New option for ${FEATURES_QUESTION}`).fill("Integrations");
  const addRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().endsWith("/api/questions/2/options") &&
      request.postDataJSON().text === "Integrations",
  );
  await page
    .getByRole("button", { name: `Add option to ${FEATURES_QUESTION}`, exact: true })
    .click();
  await addRequest;

  await expect(optionItems(page, FEATURES_QUESTION)).toContainText([
    "Export",
    "Sharing",
    "Integrations",
  ]);
  await expect(optionItems(page, HEAR_QUESTION)).toContainText(["Friend", "Search", "Advert"]);
  await expect(page.getByText("2 questions · 6 options")).toBeVisible();

  const removeRequest = page.waitForRequest(
    (request) =>
      request.method() === "DELETE" &&
      request.url().endsWith("/api/questions/2/options/1"),
  );
  await optionList(page, FEATURES_QUESTION)
    .getByRole("button", { name: `Remove option Sharing from ${FEATURES_QUESTION}`, exact: true })
    .click();
  await removeRequest;

  await expect(optionItems(page, FEATURES_QUESTION)).toContainText(["Export", "Integrations"]);
  await expect(optionItems(page, HEAR_QUESTION)).toContainText(["Friend", "Search", "Advert"]);
  await expect(page.getByText("2 questions · 5 options")).toBeVisible();

  await page.reload();
  await expect(page.getByText("2 questions · 5 options")).toBeVisible();
  await expect(optionItems(page, FEATURES_QUESTION)).toContainText(["Export", "Integrations"]);
  await expect(optionItems(page, HEAR_QUESTION)).toContainText(["Friend", "Search", "Advert"]);
});

test("reorders questions and previews the stored order with matching controls", async ({ page }) => {
  await expect(questionHeadings(page)).toHaveText([
    `Q1: ${HEAR_QUESTION}`,
    `Q2: ${FEATURES_QUESTION}`,
  ]);

  const moveUpRequest = page.waitForRequest(
    (request) =>
      request.method() === "PUT" &&
      request.url().endsWith("/api/order") &&
      request.postDataJSON().order.join(",") === "2,1",
  );
  await page
    .getByRole("button", { name: `Move question up: ${FEATURES_QUESTION}`, exact: true })
    .click();
  await moveUpRequest;

  await expect(questionHeadings(page)).toHaveText([
    `Q1: ${FEATURES_QUESTION}`,
    `Q2: ${HEAR_QUESTION}`,
  ]);

  await page.getByRole("button", { name: "Preview", exact: true }).click();
  await expect(page.getByRole("button", { name: "Hide preview", exact: true })).toBeVisible();

  const preview = page.getByRole("region", { name: "Preview", exact: true });
  const featuresPreview = preview.getByRole("group", { name: `1. ${FEATURES_QUESTION}` });
  await expect(featuresPreview.getByRole("checkbox")).toHaveCount(2);
  await expect(featuresPreview.getByRole("checkbox", { name: "Export" })).toBeVisible();
  await expect(featuresPreview.getByRole("checkbox", { name: "Sharing" })).toBeVisible();

  const hearPreview = preview.getByRole("group", { name: `2. ${HEAR_QUESTION}` });
  await expect(hearPreview.getByRole("radio")).toHaveCount(3);
  await expect(hearPreview.getByRole("radio", { name: "Friend" })).toBeVisible();
  await expect(hearPreview.getByRole("radio", { name: "Search" })).toBeVisible();
  await expect(hearPreview.getByRole("radio", { name: "Advert" })).toBeVisible();

  await page.reload();
  await expect(questionHeadings(page)).toHaveText([
    `Q1: ${FEATURES_QUESTION}`,
    `Q2: ${HEAR_QUESTION}`,
  ]);

  const moveDownRequest = page.waitForRequest(
    (request) =>
      request.method() === "PUT" &&
      request.url().endsWith("/api/order") &&
      request.postDataJSON().order.join(",") === "1,2",
  );
  await page
    .getByRole("button", { name: `Move question down: ${FEATURES_QUESTION}`, exact: true })
    .click();
  await moveDownRequest;

  await expect(questionHeadings(page)).toHaveText([
    `Q1: ${HEAR_QUESTION}`,
    `Q2: ${FEATURES_QUESTION}`,
  ]);

  await page.reload();
  await expect(questionHeadings(page)).toHaveText([
    `Q1: ${HEAR_QUESTION}`,
    `Q2: ${FEATURES_QUESTION}`,
  ]);
});

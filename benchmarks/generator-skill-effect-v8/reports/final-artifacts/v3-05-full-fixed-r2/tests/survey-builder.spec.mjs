import { expect, test } from "@playwright/test";

const counter = (page) => page.getByText(/^\d+ questions? · \d+ options?$/);
const questionHeadings = (page) => page.getByRole("heading", { level: 2 });
const optionsFor = (page, question) => page.getByRole("list", {
  name: `Options for ${question}`,
  exact: true,
});

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.status()).toBe(200);
  await page.goto("/");
  await expect(counter(page)).toHaveText("2 questions · 5 options");
});

test("adds and removes options only for the targeted question", async ({ page }) => {
  const firstQuestion = "How did you hear about us?";
  const secondQuestion = "Which features do you use?";
  const firstOptions = optionsFor(page, firstQuestion).getByRole("listitem");
  const secondOptions = optionsFor(page, secondQuestion).getByRole("listitem");

  await page.getByLabel(`New option for ${firstQuestion}`).fill("Podcast");
  const addOption = page.waitForResponse((response) => (
    response.url().endsWith("/api/questions/1/options")
    && response.request().method() === "POST"
    && response.status() === 200
  ));
  await page.getByRole("button", { name: `Add option to ${firstQuestion}`, exact: true }).click();
  await addOption;

  await expect(counter(page)).toHaveText("2 questions · 6 options");
  await expect(firstOptions).toHaveText([
    "FriendRemove option",
    "SearchRemove option",
    "AdvertRemove option",
    "PodcastRemove option",
  ]);
  await expect(secondOptions).toHaveText([
    "ExportRemove option",
    "SharingRemove option",
  ]);

  const removeOption = page.waitForResponse((response) => (
    response.url().endsWith("/api/questions/1/options/1")
    && response.request().method() === "DELETE"
    && response.status() === 200
  ));
  await page.getByRole("button", { name: `Remove option Search from ${firstQuestion}`, exact: true }).click();
  await removeOption;

  await expect(counter(page)).toHaveText("2 questions · 5 options");
  await expect(firstOptions).toHaveText([
    "FriendRemove option",
    "AdvertRemove option",
    "PodcastRemove option",
  ]);
  await expect(secondOptions).toHaveText([
    "ExportRemove option",
    "SharingRemove option",
  ]);
});

test("moves questions up and down in the builder", async ({ page }) => {
  await expect(questionHeadings(page)).toHaveText([
    "Q1: How did you hear about us?",
    "Q2: Which features do you use?",
  ]);

  const moveDown = page.waitForResponse((response) => (
    response.url().endsWith("/api/order")
    && response.request().method() === "PUT"
    && response.status() === 200
  ));
  await page.getByRole("button", { name: "Move question down: How did you hear about us?", exact: true }).click();
  await moveDown;

  await expect(questionHeadings(page)).toHaveText([
    "Q1: Which features do you use?",
    "Q2: How did you hear about us?",
  ]);

  const moveUp = page.waitForResponse((response) => (
    response.url().endsWith("/api/order")
    && response.request().method() === "PUT"
    && response.status() === 200
  ));
  await page.getByRole("button", { name: "Move question up: How did you hear about us?", exact: true }).click();
  await moveUp;

  await expect(questionHeadings(page)).toHaveText([
    "Q1: How did you hear about us?",
    "Q2: Which features do you use?",
  ]);
});

test("shows a preview with current question order and input types", async ({ page }) => {
  const reorder = page.waitForResponse((response) => (
    response.url().endsWith("/api/order")
    && response.request().method() === "PUT"
    && response.status() === 200
  ));
  await page.getByRole("button", { name: "Move question down: How did you hear about us?", exact: true }).click();
  await reorder;

  await page.getByRole("button", { name: "Preview", exact: true }).click();

  const preview = page.getByRole("region", { name: "Preview", exact: true });
  const multipleQuestion = preview.getByRole("group", { name: "1. Which features do you use?", exact: true });
  const singleQuestion = preview.getByRole("group", { name: "2. How did you hear about us?", exact: true });

  await expect(page.getByRole("button", { name: "Hide preview", exact: true })).toBeVisible();
  await expect(preview.getByRole("group")).toHaveCount(2);
  await expect(multipleQuestion.getByRole("checkbox")).toHaveCount(2);
  await expect(multipleQuestion.getByRole("checkbox", { name: "Export" })).toBeVisible();
  await expect(multipleQuestion.getByRole("checkbox", { name: "Sharing" })).toBeVisible();
  await expect(singleQuestion.getByRole("radio")).toHaveCount(3);
  await expect(singleQuestion.getByRole("radio", { name: "Friend" })).toBeVisible();
  await expect(singleQuestion.getByRole("radio", { name: "Search" })).toBeVisible();
  await expect(singleQuestion.getByRole("radio", { name: "Advert" })).toBeVisible();
});

test("persists option edits and question order after reload", async ({ page }) => {
  const firstQuestion = "How did you hear about us?";
  await page.getByLabel(`New option for ${firstQuestion}`).fill("Conference");
  const addOption = page.waitForResponse((response) => (
    response.url().endsWith("/api/questions/1/options")
    && response.request().method() === "POST"
    && response.status() === 200
  ));
  await page.getByRole("button", { name: `Add option to ${firstQuestion}`, exact: true }).click();
  await addOption;

  const reorder = page.waitForResponse((response) => (
    response.url().endsWith("/api/order")
    && response.request().method() === "PUT"
    && response.status() === 200
  ));
  await page.getByRole("button", { name: "Move question down: How did you hear about us?", exact: true }).click();
  await reorder;

  await page.reload();

  await expect(counter(page)).toHaveText("2 questions · 6 options");
  await expect(questionHeadings(page)).toHaveText([
    "Q1: Which features do you use?",
    "Q2: How did you hear about us?",
  ]);
  await expect(optionsFor(page, firstQuestion).getByRole("listitem")).toHaveText([
    "FriendRemove option",
    "SearchRemove option",
    "AdvertRemove option",
    "ConferenceRemove option",
  ]);
});

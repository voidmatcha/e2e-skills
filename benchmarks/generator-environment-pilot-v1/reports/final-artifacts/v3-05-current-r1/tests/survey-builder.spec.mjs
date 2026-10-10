import { expect, test } from "@playwright/test";

const hearQuestion = "How did you hear about us?";
const featureQuestion = "Which features do you use?";

const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const questionCard = (page, question) =>
  page.getByRole("article").filter({
    has: page.getByRole("heading", { name: new RegExp(`^Q\\d+: ${escapeRegExp(question)}$`) }),
  });

const optionsList = (page, question) => {
  return page.getByRole("list", { name: `Options for ${question}` });
};

const optionItems = (page, question) => optionsList(page, question).getByRole("listitem");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Survey builder" })).toBeVisible();
});

test("adds and removes options on the selected question only", async ({ page }) => {
  const hearCard = questionCard(page, hearQuestion);
  const featureOptions = optionsList(page, featureQuestion);
  const counter = page.getByText(/^2 questions · \d+ options$/);

  const addRequest = page.waitForRequest((request) => {
    const body = request.postDataJSON();
    return (
      request.method() === "POST" &&
      request.url().endsWith("/api/questions/1/options") &&
      body.text === "Podcast"
    );
  });
  await hearCard.getByRole("textbox", { name: `New option for ${hearQuestion}` }).fill("Podcast");
  await hearCard.getByRole("button", { name: `Add option to ${hearQuestion}` }).click();
  await addRequest;

  await expect(optionItems(page, hearQuestion)).toHaveText([
    "FriendRemove option",
    "SearchRemove option",
    "AdvertRemove option",
    "PodcastRemove option",
  ]);
  await expect(featureOptions.getByRole("listitem")).toHaveText([
    "ExportRemove option",
    "SharingRemove option",
  ]);
  await expect(counter).toHaveText("2 questions · 6 options");

  const removeRequest = page.waitForRequest((request) =>
    request.method() === "DELETE" &&
    request.url().endsWith("/api/questions/1/options/1")
  );
  await hearCard.getByRole("button", { name: `Remove option Search from ${hearQuestion}` }).click();
  await removeRequest;

  await expect(optionItems(page, hearQuestion)).toHaveText([
    "FriendRemove option",
    "AdvertRemove option",
    "PodcastRemove option",
  ]);
  await expect(featureOptions.getByRole("listitem")).toHaveText([
    "ExportRemove option",
    "SharingRemove option",
  ]);
  await expect(counter).toHaveText("2 questions · 5 options");

  await page.reload();
  await expect(optionItems(page, hearQuestion)).toHaveText([
    "FriendRemove option",
    "AdvertRemove option",
    "PodcastRemove option",
  ]);
  await expect(counter).toHaveText("2 questions · 5 options");
});

test("moves questions down and up and keeps the order after reload", async ({ page }) => {
  const headings = page.getByRole("heading", { level: 2 });
  await expect(headings).toHaveText([
    `Q1: ${hearQuestion}`,
    `Q2: ${featureQuestion}`,
  ]);

  const moveDownRequest = page.waitForRequest((request) => {
    const body = request.postDataJSON();
    return (
      request.method() === "PUT" &&
      request.url().endsWith("/api/order") &&
      JSON.stringify(body.order) === JSON.stringify([2, 1])
    );
  });
  await questionCard(page, hearQuestion)
    .getByRole("button", { name: `Move question down: ${hearQuestion}` })
    .click();
  await moveDownRequest;

  await expect(headings).toHaveText([
    `Q1: ${featureQuestion}`,
    `Q2: ${hearQuestion}`,
  ]);

  await page.reload();
  await expect(headings).toHaveText([
    `Q1: ${featureQuestion}`,
    `Q2: ${hearQuestion}`,
  ]);

  const moveUpRequest = page.waitForRequest((request) => {
    const body = request.postDataJSON();
    return (
      request.method() === "PUT" &&
      request.url().endsWith("/api/order") &&
      JSON.stringify(body.order) === JSON.stringify([1, 2])
    );
  });
  await questionCard(page, hearQuestion)
    .getByRole("button", { name: `Move question up: ${hearQuestion}` })
    .click();
  await moveUpRequest;

  await expect(headings).toHaveText([
    `Q1: ${hearQuestion}`,
    `Q2: ${featureQuestion}`,
  ]);

  await page.reload();
  await expect(headings).toHaveText([
    `Q1: ${hearQuestion}`,
    `Q2: ${featureQuestion}`,
  ]);
});

test("previews the current question order with the correct input types", async ({ page }) => {
  await questionCard(page, hearQuestion)
    .getByRole("button", { name: `Move question down: ${hearQuestion}` })
    .click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText([
    `Q1: ${featureQuestion}`,
    `Q2: ${hearQuestion}`,
  ]);

  await page.getByRole("button", { name: "Preview" }).click();

  const preview = page.getByRole("region", { name: "Preview" });
  await expect(page.getByRole("button", { name: "Hide preview" })).toBeVisible();
  await expect(preview.getByRole("group")).toHaveText([
    "1. Which features do you use?ExportSharing",
    "2. How did you hear about us?FriendSearchAdvert",
  ]);
  await expect(preview.getByRole("group", { name: `1. ${featureQuestion}` }).getByRole("checkbox")).toHaveCount(2);
  await expect(preview.getByRole("group", { name: `2. ${hearQuestion}` }).getByRole("radio")).toHaveCount(3);

  await page.reload();
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(preview.getByRole("group")).toHaveText([
    "1. Which features do you use?ExportSharing",
    "2. How did you hear about us?FriendSearchAdvert",
  ]);
});

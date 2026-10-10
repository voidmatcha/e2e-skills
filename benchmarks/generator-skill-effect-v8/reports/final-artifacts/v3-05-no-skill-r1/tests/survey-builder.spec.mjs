import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

const questionCard = (page, name) =>
  page.locator(".question").filter({
    has: page.getByRole("heading", { name: new RegExp(name) }),
  });

const optionList = (page, question) =>
  page.getByRole("list", { name: `Options for ${question}` });

test("shows the seeded questions and option count", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");
  await expect(page.getByRole("heading", { name: "Q1: How did you hear about us?" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Q2: Which features do you use?" })).toBeVisible();

  await expect(optionList(page, "How did you hear about us?").getByText("Friend")).toBeVisible();
  await expect(optionList(page, "How did you hear about us?").getByText("Search")).toBeVisible();
  await expect(optionList(page, "How did you hear about us?").getByText("Advert")).toBeVisible();
  await expect(optionList(page, "Which features do you use?").getByText("Export")).toBeVisible();
  await expect(optionList(page, "Which features do you use?").getByText("Sharing")).toBeVisible();
});

test("adds and removes options only on the selected question", async ({ page }) => {
  await page.goto("/");

  const firstQuestion = "How did you hear about us?";
  const secondQuestion = "Which features do you use?";
  const firstCard = questionCard(page, firstQuestion);

  await firstCard.getByLabel(`New option for ${firstQuestion}`).fill("Podcast");
  await firstCard.getByRole("button", { name: `Add option to ${firstQuestion}` }).click();

  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 6 options");
  await expect(optionList(page, firstQuestion).getByText("Podcast")).toBeVisible();
  await expect(optionList(page, secondQuestion).getByText("Podcast")).toHaveCount(0);
  await expect(optionList(page, firstQuestion).getByRole("listitem")).toHaveCount(4);
  await expect(optionList(page, secondQuestion).getByRole("listitem")).toHaveCount(2);

  await firstCard.getByRole("button", { name: `Remove option Search from ${firstQuestion}` }).click();

  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");
  await expect(optionList(page, firstQuestion).getByText("Search")).toHaveCount(0);
  await expect(optionList(page, firstQuestion).getByText("Friend")).toBeVisible();
  await expect(optionList(page, firstQuestion).getByText("Advert")).toBeVisible();
  await expect(optionList(page, firstQuestion).getByText("Podcast")).toBeVisible();
  await expect(optionList(page, secondQuestion).getByText("Export")).toBeVisible();
  await expect(optionList(page, secondQuestion).getByText("Sharing")).toBeVisible();
});

test("reorders questions with move up and move down", async ({ page }) => {
  await page.goto("/");

  await questionCard(page, "How did you hear about us?").getByRole("button", { name: /Move question down/ }).click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText([
    "Q1: Which features do you use?",
    "Q2: How did you hear about us?",
  ]);

  await questionCard(page, "How did you hear about us?").getByRole("button", { name: /Move question up/ }).click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText([
    "Q1: How did you hear about us?",
    "Q2: Which features do you use?",
  ]);
});

test("previews the current order and persists options and order after reload", async ({ page }) => {
  await page.goto("/");

  const firstQuestion = "How did you hear about us?";
  const secondQuestion = "Which features do you use?";
  await questionCard(page, firstQuestion).getByLabel(`New option for ${firstQuestion}`).fill("Podcast");
  await questionCard(page, firstQuestion).getByRole("button", { name: `Add option to ${firstQuestion}` }).click();
  await questionCard(page, firstQuestion).getByRole("button", { name: /Move question down/ }).click();

  await page.getByRole("button", { name: "Preview" }).click();

  await expect(page.getByRole("button", { name: "Hide preview" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Preview" })).toBeVisible();
  await expect(page.getByRole("group")).toHaveText([
    /1\. Which features do you use\?ExportSharing/,
    /2\. How did you hear about us\?FriendSearchAdvertPodcast/,
  ]);
  await expect(page.getByRole("checkbox", { name: "Export" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Sharing" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Friend" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Search" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Advert" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Podcast" })).toBeVisible();

  await page.reload();

  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 6 options");
  await expect(page.getByRole("heading", { level: 2 })).toHaveText([
    "Q1: Which features do you use?",
    "Q2: How did you hear about us?",
  ]);
  await expect(optionList(page, firstQuestion).getByText("Podcast")).toBeVisible();
});

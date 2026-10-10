import { expect, test } from "@playwright/test";

const questionHeadings = (page) => page.locator("article.question h2");

const questionCard = (page, name) =>
  page.locator("article.question").filter({
    has: page.getByRole("heading", { name: new RegExp(name) }),
  });

const optionTexts = (card) => card.locator(".option-text");

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("edits options, reorders questions, previews, and persists changes", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");
  await expect(questionHeadings(page)).toHaveText([
    "Q1: How did you hear about us?",
    "Q2: Which features do you use?",
  ]);

  const hearAbout = questionCard(page, "How did you hear about us\\?");
  const features = questionCard(page, "Which features do you use\\?");

  await hearAbout.getByRole("textbox", { name: "New option for How did you hear about us?" }).fill("Newsletter");
  await hearAbout.getByRole("button", { name: "Add option to How did you hear about us?" }).click();

  await expect(optionTexts(hearAbout)).toHaveText(["Friend", "Search", "Advert", "Newsletter"]);
  await expect(optionTexts(features)).toHaveText(["Export", "Sharing"]);
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 6 options");

  await features.getByRole("button", { name: "Remove option Export from Which features do you use?" }).click();

  await expect(optionTexts(hearAbout)).toHaveText(["Friend", "Search", "Advert", "Newsletter"]);
  await expect(optionTexts(features)).toHaveText(["Sharing"]);
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");

  await hearAbout.getByRole("button", { name: "Move question down: How did you hear about us?" }).click();
  await expect(questionHeadings(page)).toHaveText([
    "Q1: Which features do you use?",
    "Q2: How did you hear about us?",
  ]);

  await hearAbout.getByRole("button", { name: "Move question up: How did you hear about us?" }).click();
  await expect(questionHeadings(page)).toHaveText([
    "Q1: How did you hear about us?",
    "Q2: Which features do you use?",
  ]);

  await features.getByRole("button", { name: "Move question up: Which features do you use?" }).click();
  await expect(questionHeadings(page)).toHaveText([
    "Q1: Which features do you use?",
    "Q2: How did you hear about us?",
  ]);

  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("button", { name: "Hide preview" })).toBeVisible();

  const preview = page.getByRole("region", { name: "Preview" });
  await expect(preview.getByRole("group")).toHaveCount(2);

  const featuresPreview = preview.getByRole("group", { name: "1. Which features do you use?" });
  await expect(featuresPreview.getByRole("checkbox", { name: "Sharing" })).toBeVisible();
  await expect(featuresPreview.getByRole("checkbox", { name: "Export" })).toHaveCount(0);

  const hearAboutPreview = preview.getByRole("group", { name: "2. How did you hear about us?" });
  await expect(hearAboutPreview.getByRole("radio", { name: "Friend" })).toBeVisible();
  await expect(hearAboutPreview.getByRole("radio", { name: "Search" })).toBeVisible();
  await expect(hearAboutPreview.getByRole("radio", { name: "Advert" })).toBeVisible();
  await expect(hearAboutPreview.getByRole("radio", { name: "Newsletter" })).toBeVisible();

  await page.reload();

  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");
  await expect(questionHeadings(page)).toHaveText([
    "Q1: Which features do you use?",
    "Q2: How did you hear about us?",
  ]);
  await expect(optionTexts(questionCard(page, "Which features do you use\\?"))).toHaveText(["Sharing"]);
  await expect(optionTexts(questionCard(page, "How did you hear about us\\?"))).toHaveText([
    "Friend",
    "Search",
    "Advert",
    "Newsletter",
  ]);
});

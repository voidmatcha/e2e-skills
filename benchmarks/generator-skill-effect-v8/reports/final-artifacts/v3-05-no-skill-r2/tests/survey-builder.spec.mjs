import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("adds and removes options for one question and keeps the changes after reload", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("2 questions · 5 options")).toBeVisible();

  const firstQuestion = page.getByRole("article").filter({ hasText: "How did you hear about us?" });
  const secondQuestion = page.getByRole("article").filter({ hasText: "Which features do you use?" });

  await firstQuestion.getByLabel("New option for How did you hear about us?").fill("Podcast");
  await firstQuestion.getByRole("button", { name: "Add option to How did you hear about us?" }).click();

  await expect(firstQuestion.getByText("Podcast")).toBeVisible();
  await expect(secondQuestion.getByText("Podcast")).toHaveCount(0);
  await expect(page.getByText("2 questions · 6 options")).toBeVisible();

  await firstQuestion.getByRole("button", { name: "Remove option Search from How did you hear about us?" }).click();

  await expect(firstQuestion.getByText("Search")).toHaveCount(0);
  await expect(firstQuestion.getByText("Friend")).toBeVisible();
  await expect(firstQuestion.getByText("Advert")).toBeVisible();
  await expect(firstQuestion.getByText("Podcast")).toBeVisible();
  await expect(secondQuestion.getByText("Export")).toBeVisible();
  await expect(secondQuestion.getByText("Sharing")).toBeVisible();
  await expect(page.getByText("2 questions · 5 options")).toBeVisible();

  await page.reload();

  const reloadedFirstQuestion = page.getByRole("article").filter({ hasText: "How did you hear about us?" });
  const reloadedSecondQuestion = page.getByRole("article").filter({ hasText: "Which features do you use?" });

  await expect(page.getByText("2 questions · 5 options")).toBeVisible();
  await expect(reloadedFirstQuestion.getByText("Search")).toHaveCount(0);
  await expect(reloadedFirstQuestion.getByText("Podcast")).toBeVisible();
  await expect(reloadedSecondQuestion.getByText("Export")).toBeVisible();
});

test("reorders questions and previews the saved order with the right input types", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Move question up: Which features do you use?" }).click();

  await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText("Q1: Which features do you use?");
  await expect(page.getByRole("heading", { level: 2 }).nth(1)).toHaveText("Q2: How did you hear about us?");

  await page.getByRole("button", { name: "Preview" }).click();

  await expect(page.getByRole("button", { name: "Hide preview" })).toBeVisible();
  await expect(page.getByLabel("Preview")).toBeVisible();
  await expect(page.getByRole("group").first()).toContainText("1. Which features do you use?");
  await expect(page.getByRole("group").nth(1)).toContainText("2. How did you hear about us?");
  await expect(page.getByRole("checkbox", { name: "Export" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Sharing" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Friend" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Search" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Advert" })).toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText("Q1: Which features do you use?");
  await expect(page.getByRole("heading", { level: 2 }).nth(1)).toHaveText("Q2: How did you hear about us?");

  await page.getByRole("button", { name: "Move question down: Which features do you use?" }).click();

  await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText("Q1: How did you hear about us?");
  await expect(page.getByRole("heading", { level: 2 }).nth(1)).toHaveText("Q2: Which features do you use?");
});

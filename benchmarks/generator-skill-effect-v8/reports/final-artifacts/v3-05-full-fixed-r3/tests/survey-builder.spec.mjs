import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds and removes options for only the selected question", async ({ page }) => {
  const firstQuestion = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: "Q1: How did you hear about us?", exact: true }) });
  const secondQuestionOptions = page.getByRole("list", { name: "Options for Which features do you use?", exact: true });

  await expect(page.getByText("2 questions · 5 options")).toBeVisible();

  const addRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().endsWith("/api/questions/1/options") &&
      request.postDataJSON().text === "Podcast",
  );
  await firstQuestion.getByLabel("New option for How did you hear about us?").fill("Podcast");
  await firstQuestion.getByRole("button", { name: "Add option to How did you hear about us?" }).click();
  await addRequest;

  await expect(page.getByRole("list", { name: "Options for How did you hear about us?", exact: true }).getByRole("listitem")).toHaveText([
    /Friend/,
    /Search/,
    /Advert/,
    /Podcast/,
  ]);
  await expect(secondQuestionOptions.getByRole("listitem")).toHaveText([/Export/, /Sharing/]);
  await expect(page.getByText("2 questions · 6 options")).toBeVisible();

  const removeRequest = page.waitForRequest(
    (request) => request.method() === "DELETE" && request.url().endsWith("/api/questions/1/options/1"),
  );
  await firstQuestion.getByRole("button", { name: "Remove option Search from How did you hear about us?" }).click();
  await removeRequest;

  await expect(page.getByRole("list", { name: "Options for How did you hear about us?", exact: true }).getByRole("listitem")).toHaveText([
    /Friend/,
    /Advert/,
    /Podcast/,
  ]);
  await expect(secondQuestionOptions.getByRole("listitem")).toHaveText([/Export/, /Sharing/]);
  await expect(page.getByText("2 questions · 5 options")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("list", { name: "Options for How did you hear about us?", exact: true }).getByRole("listitem")).toHaveText([
    /Friend/,
    /Advert/,
    /Podcast/,
  ]);
  await expect(secondQuestionOptions.getByRole("listitem")).toHaveText([/Export/, /Sharing/]);
  await expect(page.getByText("2 questions · 5 options")).toBeVisible();
});

test("reorders questions and previews the current survey", async ({ page }) => {
  const firstQuestion = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: "Q1: How did you hear about us?", exact: true }) });

  const orderRequest = page.waitForRequest(
    (request) =>
      request.method() === "PUT" &&
      request.url().endsWith("/api/order") &&
      JSON.stringify(request.postDataJSON().order) === JSON.stringify([2, 1]),
  );
  await firstQuestion.getByRole("button", { name: "Move question down: How did you hear about us?" }).click();
  await orderRequest;

  await expect(page.getByRole("heading", { level: 2 })).toHaveText([
    "Q1: Which features do you use?",
    "Q2: How did you hear about us?",
  ]);
  await expect(page.getByText("2 questions · 5 options")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText([
    "Q1: Which features do you use?",
    "Q2: How did you hear about us?",
  ]);

  const movedQuestion = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: "Q2: How did you hear about us?", exact: true }) });
  const restoreOrderRequest = page.waitForRequest(
    (request) =>
      request.method() === "PUT" &&
      request.url().endsWith("/api/order") &&
      JSON.stringify(request.postDataJSON().order) === JSON.stringify([1, 2]),
  );
  await movedQuestion.getByRole("button", { name: "Move question up: How did you hear about us?" }).click();
  await restoreOrderRequest;

  await expect(page.getByRole("heading", { level: 2 })).toHaveText([
    "Q1: How did you hear about us?",
    "Q2: Which features do you use?",
  ]);

  await page.getByRole("button", { name: "Preview", exact: true }).click();

  const preview = page.getByRole("region", { name: "Preview", exact: true });
  await expect(page.getByRole("button", { name: "Hide preview", exact: true })).toBeVisible();
  await expect(preview).toBeVisible();
  await expect(preview.getByRole("group")).toHaveText([
    /1\. How did you hear about us?[\s\S]*Friend[\s\S]*Search[\s\S]*Advert/,
    /2\. Which features do you use?[\s\S]*Export[\s\S]*Sharing/,
  ]);
  await expect(preview.getByRole("radio")).toHaveCount(3);
  await expect(preview.getByRole("checkbox")).toHaveCount(2);

  await page.reload();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText([
    "Q1: How did you hear about us?",
    "Q2: Which features do you use?",
  ]);
  await page.getByRole("button", { name: "Preview", exact: true }).click();
  await expect(page.getByRole("region", { name: "Preview", exact: true }).getByRole("group")).toHaveText([
    /1\. How did you hear about us?[\s\S]*Friend[\s\S]*Search[\s\S]*Advert/,
    /2\. Which features do you use?[\s\S]*Export[\s\S]*Sharing/,
  ]);
});

import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
});

const next = (page) => page.getByRole("button", { name: "Next" });
const previous = (page) => page.getByRole("button", { name: "Previous" });
const submit = (page) => page.getByRole("button", { name: "Submit" });

async function answerAll(page, [a, b, c]) {
  await page.getByLabel(a, { exact: true }).check();
  await next(page).click();
  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await page.getByLabel(b, { exact: true }).check();
  await next(page).click();
  await expect(page.getByText("Question 3 of 3")).toBeVisible();
  await page.getByLabel(c, { exact: true }).check();
  await submit(page).click();
}

test("Next is disabled until an answer is chosen", async ({ page }) => {
  await expect(next(page)).toBeDisabled();
  await page.getByLabel("Jupiter").check();
  await expect(next(page)).toBeEnabled();
});

test("Previous returns to the earlier question with its answer selected", async ({ page }) => {
  await expect(previous(page)).toBeDisabled();
  await page.getByLabel("Mars").check();
  await next(page).click();
  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await expect(next(page)).toBeDisabled();
  await previous(page).click();
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByLabel("Mars")).toBeChecked();
});

test("Submit replaces Next on the last question", async ({ page }) => {
  await expect(submit(page)).toBeHidden();
  await page.getByLabel("Jupiter").check();
  await next(page).click();
  await page.getByLabel("Canberra").check();
  await next(page).click();
  await expect(page.getByText("Question 3 of 3")).toBeVisible();
  await expect(next(page)).toBeHidden();
  await expect(submit(page)).toBeVisible();
  await expect(submit(page)).toBeDisabled();
  await page.getByLabel("6", { exact: true }).check();
  await expect(submit(page)).toBeEnabled();
});

test("all correct answers score 3 of 3", async ({ page }) => {
  await answerAll(page, ["Jupiter", "Canberra", "6"]);
  await expect(page.getByText("You scored 3 of 3")).toBeVisible();
});

test("partially correct answers score 1 of 3", async ({ page }) => {
  await answerAll(page, ["Jupiter", "Sydney", "8"]);
  await expect(page.getByText("You scored 1 of 3")).toBeVisible();
});

test("all wrong answers score 0 of 3", async ({ page }) => {
  await answerAll(page, ["Mars", "Sydney", "8"]);
  await expect(page.getByText("You scored 0 of 3")).toBeVisible();
});

test("no last score is shown before any submission", async ({ page }) => {
  await expect(page.getByText("Your last score")).toHaveCount(0);
});

test("the score is stored and shown after a reload", async ({ page }) => {
  await answerAll(page, ["Jupiter", "Canberra", "8"]);
  await expect(page.getByText("You scored 2 of 3")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Your last score: 2 of 3")).toBeVisible();
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
});

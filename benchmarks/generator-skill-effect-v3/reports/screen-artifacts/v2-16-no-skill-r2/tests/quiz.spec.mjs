import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request, page }) => {
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
  await page.getByLabel(b, { exact: true }).check();
  await next(page).click();
  await page.getByLabel(c, { exact: true }).check();
  await submit(page).click();
}

test("starts on question 1 with Next disabled and no last score", async ({ page }) => {
  await expect(page.getByText("Which planet is the largest?")).toBeVisible();
  await expect(next(page)).toBeDisabled();
  await expect(previous(page)).toBeDisabled();
  await expect(page.getByRole("status")).toHaveText("");
});

test("Next enables once an answer is chosen and advances", async ({ page }) => {
  await page.getByLabel("Jupiter").check();
  await expect(next(page)).toBeEnabled();
  await next(page).click();
  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await expect(page.getByText("What is the capital of Australia?")).toBeVisible();
  await expect(next(page)).toBeDisabled();
});

test("Previous returns to the earlier question with its answer selected", async ({ page }) => {
  await page.getByLabel("Mars").check();
  await next(page).click();
  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await previous(page).click();
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByLabel("Mars")).toBeChecked();
  await expect(next(page)).toBeEnabled();
});

test("Submit replaces Next on the last question and needs an answer", async ({ page }) => {
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

test("mixed answers score 1 of 3", async ({ page }) => {
  await answerAll(page, ["Jupiter", "Sydney", "8"]);
  await expect(page.getByText("You scored 1 of 3")).toBeVisible();
});

test("all wrong answers score 0 of 3", async ({ page }) => {
  await answerAll(page, ["Mars", "Sydney", "8"]);
  await expect(page.getByText("You scored 0 of 3")).toBeVisible();
});

test("the score is stored and shown after a reload", async ({ page }) => {
  await answerAll(page, ["Jupiter", "Canberra", "8"]);
  await expect(page.getByText("You scored 2 of 3")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByText("Your last score: 2 of 3")).toBeVisible();
});

import { expect, test } from "@playwright/test";

const next = (page) => page.getByRole("button", { name: "Next" });
const previous = (page) => page.getByRole("button", { name: "Previous" });
const submit = (page) => page.getByRole("button", { name: "Submit" });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
});

test("next needs an answer and previous keeps it", async ({ page }) => {
  await expect(next(page)).toBeDisabled();
  await expect(previous(page)).toBeDisabled();
  await page.getByLabel("Jupiter").check();
  await expect(next(page)).toBeEnabled();
  await next(page).click();
  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await expect(next(page)).toBeDisabled();
  await previous(page).click();
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByLabel("Jupiter")).toBeChecked();
  await expect(next(page)).toBeEnabled();
});

test("submit scores the chosen answers and the score survives a reload", async ({ page }) => {
  await page.getByLabel("Jupiter").check();
  await next(page).click();
  await page.getByLabel("Canberra").check();
  await next(page).click();
  await expect(page.getByText("Question 3 of 3")).toBeVisible();
  await expect(next(page)).toBeHidden();
  await expect(submit(page)).toBeDisabled();
  await page.getByLabel("6", { exact: true }).check();
  await submit(page).click();
  await expect(page.getByRole("heading", { name: "You scored 3 of 3" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Your last score: 3 of 3");
});

test("wrong answers lower the score", async ({ page }) => {
  await page.getByLabel("Mars").check();
  await next(page).click();
  await page.getByLabel("Canberra").check();
  await next(page).click();
  await page.getByLabel("8", { exact: true }).check();
  await submit(page).click();
  await expect(page.getByRole("heading", { name: "You scored 1 of 3" })).toBeVisible();
});

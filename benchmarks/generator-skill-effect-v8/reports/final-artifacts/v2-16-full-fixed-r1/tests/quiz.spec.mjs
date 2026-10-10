import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("requires an answer before advancing and preserves the previous answer", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByRole("group", { name: "Which planet is the largest?", exact: true })).toBeVisible();

  const nextButton = page.getByRole("button", { name: "Next", exact: true });
  await expect(page.getByRole("button", { name: "Previous", exact: true })).toBeDisabled();
  await expect(nextButton).toBeDisabled();

  await page.getByLabel("Mars").check();
  await expect(nextButton).toBeEnabled();
  await nextButton.click();

  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await expect(page.getByRole("group", { name: "What is the capital of Australia?", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Previous", exact: true }).click();

  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByLabel("Mars")).toBeChecked();
  await expect(nextButton).toBeEnabled();
});

test("submits the quiz and shows the saved last score after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Jupiter").check();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel("Canberra").check();
  await page.getByRole("button", { name: "Next", exact: true }).click();

  await expect(page.getByText("Question 3 of 3")).toBeVisible();
  const submitButton = page.getByRole("button", { name: "Submit", exact: true });
  await expect(submitButton).toBeVisible();
  await expect(submitButton).toBeDisabled();

  await page.getByLabel("6").check();
  await expect(submitButton).toBeEnabled();
  await submitButton.click();

  await expect(page.getByRole("heading", { name: "You scored 3 of 3", exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Your last score: 3 of 3");
});

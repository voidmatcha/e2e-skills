import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("requires an answer before advancing and keeps answers when going back", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByRole("group", { name: "Which planet is the largest?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Previous" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();

  await page.getByLabel("Jupiter").check();
  await expect(page.getByRole("button", { name: "Next" })).toBeEnabled();
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await expect(page.getByRole("group", { name: "What is the capital of Australia?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Previous" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();

  await page.getByLabel("Canberra").check();
  await page.getByRole("button", { name: "Previous" }).click();

  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByLabel("Jupiter")).toBeChecked();
  await expect(page.getByRole("button", { name: "Next" })).toBeEnabled();
});

test("submits the completed quiz and shows the last score after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Jupiter").check();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Canberra").check();
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByText("Question 3 of 3")).toBeVisible();
  await expect(page.getByRole("group", { name: "What is 2 + 2 × 2?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Submit" })).toBeDisabled();

  await page.getByLabel("6").check();
  await expect(page.getByRole("button", { name: "Submit" })).toBeEnabled();
  await page.getByRole("button", { name: "Submit" }).click();

  await expect(page.getByRole("heading", { name: "You scored 3 of 3" })).toBeVisible();

  await page.reload();

  await expect(page.getByText("Your last score: 3 of 3")).toBeVisible();
});

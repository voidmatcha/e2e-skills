import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("completes the quiz and remembers the last score", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Previous" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();

  await page.getByLabel("Jupiter").check();
  await expect(page.getByRole("button", { name: "Next" })).toBeEnabled();
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Previous" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();

  await page.getByLabel("Sydney").check();
  await page.getByRole("button", { name: "Previous" }).click();

  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByLabel("Jupiter")).toBeChecked();

  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await expect(page.getByLabel("Sydney")).toBeChecked();
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByText("Question 3 of 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Next" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Submit" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit" })).toBeDisabled();

  await page.getByLabel("6").check();
  await expect(page.getByRole("button", { name: "Submit" })).toBeEnabled();
  await page.getByRole("button", { name: "Submit" }).click();

  await expect(page.getByRole("heading", { name: "You scored 2 of 3" })).toBeVisible();

  await page.reload();
  await expect(page.getByText("Your last score: 2 of 3")).toBeVisible();
});

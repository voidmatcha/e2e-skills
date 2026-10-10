import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("keeps navigation locked until an answer is selected and preserves answers", async ({ page }) => {
  await page.goto("/");

  const nextButton = page.getByRole("button", { name: "Next", exact: true });
  const previousButton = page.getByRole("button", { name: "Previous", exact: true });

  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(nextButton).toBeDisabled();

  await page.getByLabel("Jupiter").check();
  await expect(nextButton).toBeEnabled();
  await nextButton.click();

  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await page.getByLabel("Canberra").check();
  await previousButton.click();

  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByLabel("Jupiter")).toBeChecked();
});

test("submits the selected answers and shows the last score after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Jupiter").check();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel("Canberra").check();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel("6").check();

  const submitButton = page.getByRole("button", { name: "Submit", exact: true });
  await expect(submitButton).toBeVisible();

  const submissionRequest = page.waitForRequest(
    (request) => request.url().endsWith("/api/submissions") && request.method() === "POST",
  );
  const submissionResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/submissions") && response.request().method() === "POST",
  );
  await submitButton.click();
  const request = await submissionRequest;
  const response = await submissionResponse;

  expect(JSON.parse(request.postData())).toEqual({
    answers: { q1: "Jupiter", q2: "Canberra", q3: "6" },
  });
  expect(response.status()).toBe(201);

  await expect(page.getByRole("heading", { name: "You scored 3 of 3", exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Your last score: 3 of 3");
});

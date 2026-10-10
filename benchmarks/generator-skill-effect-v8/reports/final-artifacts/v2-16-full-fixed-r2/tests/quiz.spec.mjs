import { expect, test } from "@playwright/test";

const submissionRequest = (page) =>
  page.waitForRequest((request) =>
    request.url().endsWith("/api/submissions") &&
    request.method() === "POST"
  );

const submissionResponse = (page) =>
  page.waitForResponse((response) =>
    response.url().endsWith("/api/submissions") &&
    response.request().method() === "POST"
  );

async function chooseAnswer(page, answer) {
  await page.getByRole("radio", { name: answer, exact: true }).check();
}

async function submitAnswers(page, answers) {
  for (const answer of answers.slice(0, -1)) {
    await chooseAnswer(page, answer);
    await page.getByRole("button", { name: "Next", exact: true }).click();
  }

  await chooseAnswer(page, answers.at(-1));
  const submitted = submissionRequest(page);
  const response = submissionResponse(page);
  await page.getByRole("button", { name: "Submit", exact: true }).click();
  const request = await submitted;
  expect((await response).status()).toBe(201);
  expect(JSON.parse(request.postData() ?? "{}")).toEqual({
    answers: { q1: answers[0], q2: answers[1], q3: answers[2] },
  });
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("keeps the chosen answer when navigating back through the quiz", async ({ page }) => {
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeDisabled();

  await chooseAnswer(page, "Jupiter");
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Next", exact: true }).click();

  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await chooseAnswer(page, "Canberra");
  await page.getByRole("button", { name: "Previous", exact: true }).click();

  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByRole("radio", { name: "Jupiter", exact: true })).toBeChecked();
});

test("scores submitted answers and shows the saved score after reload", async ({ page }) => {
  await submitAnswers(page, ["Jupiter", "Canberra", "6"]);

  await expect(page.getByRole("heading", { name: "You scored 3 of 3", exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Your last score: 3 of 3");
});

import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
});

const answer = (page, name) => page.getByRole("radio", { name }).check();

async function finish(page, [a, b, c]) {
  await answer(page, a);
  await page.getByRole("button", { name: "Next" }).click();
  await answer(page, b);
  await page.getByRole("button", { name: "Next" }).click();
  await answer(page, c);
  await page.getByRole("button", { name: "Submit" }).click();
}

test("shows one question at a time with progress", async ({ page }) => {
  await expect(page.getByText("Which planet is the largest?")).toBeVisible();
  await expect(page.getByRole("radio")).toHaveCount(3);
  await expect(page.getByRole("button", { name: "Previous" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Submit" })).toBeHidden();
});

test("Next is disabled until an answer is chosen", async ({ page }) => {
  const next = page.getByRole("button", { name: "Next" });
  await expect(next).toBeDisabled();
  await answer(page, "Mars");
  await expect(next).toBeEnabled();
  await next.click();
  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await expect(next).toBeDisabled();
});

test("Previous returns to the earlier question with its answer selected", async ({ page }) => {
  await answer(page, "Jupiter");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Previous" }).click();
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByRole("radio", { name: "Jupiter" })).toBeChecked();
});

test("Submit replaces Next on the last question", async ({ page }) => {
  await answer(page, "Jupiter");
  await page.getByRole("button", { name: "Next" }).click();
  await answer(page, "Canberra");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Question 3 of 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Next" })).toBeHidden();
  const submit = page.getByRole("button", { name: "Submit" });
  await expect(submit).toBeDisabled();
  await answer(page, "6");
  await expect(submit).toBeEnabled();
});

test("all correct answers score 3 of 3", async ({ page }) => {
  await finish(page, ["Jupiter", "Canberra", "6"]);
  await expect(page.getByText("You scored 3 of 3")).toBeVisible();
});

test("mixed answers score 1 of 3", async ({ page }) => {
  await finish(page, ["Jupiter", "Sydney", "8"]);
  await expect(page.getByText("You scored 1 of 3")).toBeVisible();
});

test("all wrong answers score 0 of 3", async ({ page }) => {
  await finish(page, ["Mars", "Sydney", "4"]);
  await expect(page.getByText("You scored 0 of 3")).toBeVisible();
});

test("changing an answer via Previous is reflected in the score", async ({ page }) => {
  await answer(page, "Mars");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Previous" }).click();
  await answer(page, "Jupiter");
  await page.getByRole("button", { name: "Next" }).click();
  await answer(page, "Canberra");
  await page.getByRole("button", { name: "Next" }).click();
  await answer(page, "4");
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText("You scored 2 of 3")).toBeVisible();
});

test("no last score is shown before any submission", async ({ page }) => {
  await expect(page.getByText("Your last score")).toHaveCount(0);
});

test("the score is remembered after a reload", async ({ page }) => {
  await finish(page, ["Jupiter", "Sydney", "6"]);
  await expect(page.getByText("You scored 2 of 3")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Your last score: 2 of 3")).toBeVisible();
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
});

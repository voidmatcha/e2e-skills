import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#qz-progress")).toHaveText("Question 1 of 3");
});

async function answerAll(page, [a, b, c]) {
  await page.getByLabel(a).check();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel(b).check();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel(c).check();
  await page.getByRole("button", { name: "Submit" }).click();
}

test("Next is disabled until an answer is chosen", async ({ page }) => {
  const next = page.getByRole("button", { name: "Next" });
  await expect(next).toBeDisabled();
  await page.getByLabel("Mars").check();
  await expect(next).toBeEnabled();
  await next.click();
  await expect(page.getByText("Question 2 of 3")).toBeVisible();
  await expect(next).toBeDisabled();
});

test("Previous returns to the earlier question with its answer selected", async ({ page }) => {
  const previous = page.getByRole("button", { name: "Previous" });
  await expect(previous).toBeDisabled();
  await page.getByLabel("Jupiter").check();
  await page.getByRole("button", { name: "Next" }).click();
  await previous.click();
  await expect(page.getByText("Question 1 of 3")).toBeVisible();
  await expect(page.getByLabel("Jupiter")).toBeChecked();
});

test("Submit replaces Next on the last question", async ({ page }) => {
  await page.getByLabel("Jupiter").check();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Canberra").check();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Question 3 of 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Next" })).toBeHidden();
  const submit = page.getByRole("button", { name: "Submit" });
  await expect(submit).toBeVisible();
  await expect(submit).toBeDisabled();
  await page.getByLabel("6").check();
  await expect(submit).toBeEnabled();
});

for (const [name, answers, score] of [
  ["all correct", ["Jupiter", "Canberra", "6"], 3],
  ["two correct", ["Jupiter", "Canberra", "8"], 2],
  ["one correct", ["Mars", "Canberra", "8"], 1],
  ["none correct", ["Mars", "Sydney", "4"], 0],
]) {
  test(`submitting shows the score: ${name}`, async ({ page }) => {
    await answerAll(page, answers);
    await expect(page.getByText(`You scored ${score} of 3`)).toBeVisible();
  });
}

test("no last score is shown before any submission", async ({ page }) => {
  await expect(page.getByText("Your last score")).toBeHidden();
});

test("the score is stored and shown after a reload", async ({ page }) => {
  await answerAll(page, ["Jupiter", "Sydney", "6"]);
  await expect(page.getByText("You scored 2 of 3")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Your last score: 2 of 3")).toBeVisible();
  await expect(page.locator("#qz-progress")).toHaveText("Question 1 of 3");
});

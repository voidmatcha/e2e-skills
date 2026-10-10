import { expect, test } from "@playwright/test";

const results = (page) => page.getByRole("list", { name: "Results" });
const vote = (page) => page.getByRole("button", { name: "Vote" });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("voting shows the results with counts and percentages", async ({ page }) => {
  await expect(results(page)).toBeHidden();
  await page.getByLabel("Vim").check();
  await vote(page).click();
  await expect(results(page)).toBeVisible();
  await expect(results(page).getByRole("listitem")).toHaveText(["Vim: 1 vote (100%)", "Emacs: 0 votes (0%)", "VS Code: 0 votes (0%)"]);
});

test("results stay hidden until the visitor votes", async ({ page }) => {
  await expect(results(page)).toBeHidden();
  await expect(page.getByRole("heading", { name: "Results" })).toBeHidden();
  await page.getByLabel("Emacs").check();
  await expect(results(page)).toBeHidden();
});

test("voting disables the controls and thanks the visitor", async ({ page }) => {
  await page.getByLabel("VS Code").check();
  await vote(page).click();
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  await expect(vote(page)).toBeDisabled();
  await expect(page.getByLabel("Vim")).toBeDisabled();
  await expect(page.getByLabel("Emacs")).toBeDisabled();
  await expect(page.getByLabel("VS Code")).toBeDisabled();
});

test("the vote survives a reload", async ({ page }) => {
  await page.getByLabel("Vim").check();
  await vote(page).click();
  await expect(results(page).getByRole("listitem").first()).toHaveText("Vim: 1 vote (100%)");
  await page.reload();
  await expect(results(page)).toBeVisible();
  await expect(results(page).getByRole("listitem").first()).toHaveText("Vim: 1 vote (100%)");
  await expect(vote(page)).toBeDisabled();
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
});

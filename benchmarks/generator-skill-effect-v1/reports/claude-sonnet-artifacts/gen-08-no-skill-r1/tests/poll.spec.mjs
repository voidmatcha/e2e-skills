import { expect, test } from "@playwright/test";

const OPTIONS = ["Vim", "Emacs", "VS Code"];

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByRole("radio")).toHaveCount(OPTIONS.length);
});

async function vote(page, option) {
  await page.getByLabel(option, { exact: true }).check();
  await page.getByRole("button", { name: "Vote" }).click();
}

test("hides the results until the visitor has voted", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Results" })).toBeHidden();
  await expect(page.getByRole("list", { name: "Results" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Vote" })).toBeEnabled();
});

test("voting shows one result line per option", async ({ page }) => {
  await vote(page, "Vim");
  const items = page.getByRole("list", { name: "Results" }).getByRole("listitem");
  await expect(items).toHaveText(["Vim: 1 vote (100%)", "Emacs: 0 votes (0%)", "VS Code: 0 votes (0%)"]);
});

test("voting disables the form and thanks the visitor", async ({ page }) => {
  await vote(page, "Emacs");
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
  for (const option of OPTIONS) {
    await expect(page.getByLabel(option, { exact: true })).toBeDisabled();
  }
});

test("the vote persists on the server across a reload", async ({ page }) => {
  await vote(page, "VS Code");
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  await page.reload();
  await expect(page.getByRole("radio")).toHaveCount(OPTIONS.length);

  const items = page.getByRole("list", { name: "Results" }).getByRole("listitem");
  await expect(items).toHaveText(["Vim: 0 votes (0%)", "Emacs: 0 votes (0%)", "VS Code: 1 vote (100%)"]);
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
  for (const option of OPTIONS) {
    await expect(page.getByLabel(option, { exact: true })).toBeDisabled();
  }
});

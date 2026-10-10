import { expect, test } from "@playwright/test";

const OPTIONS = ["Vim", "Emacs", "VS Code"];

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("radio", { name: "Vim" })).toBeVisible();
});

async function vote(page, option) {
  await page.getByRole("radio", { name: option }).check();
  await page.getByRole("button", { name: "Vote" }).click();
}

test("hides the results until the visitor has voted", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Results" })).toBeHidden();
  await expect(page.getByRole("list", { name: "Results" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Vote" })).toBeEnabled();
  await expect(page.getByText("Thanks for voting")).toBeHidden();
});

test("shows one result line per option after voting", async ({ page }) => {
  await vote(page, "Vim");
  const items = page.getByRole("list", { name: "Results" }).getByRole("listitem");
  await expect(items).toHaveText(["Vim: 1 vote (100%)", "Emacs: 0 votes (0%)", "VS Code: 0 votes (0%)"]);
});

test("disables the form and thanks the visitor after voting", async ({ page }) => {
  await vote(page, "Emacs");
  await expect(page.getByText("Thanks for voting")).toBeVisible();
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
  for (const option of OPTIONS) {
    await expect(page.getByRole("radio", { name: option })).toBeDisabled();
  }
});

test("keeps the vote on the server across a reload", async ({ page }) => {
  await vote(page, "VS Code");
  await expect(page.getByText("Thanks for voting")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Thanks for voting")).toBeVisible();
  const items = page.getByRole("list", { name: "Results" }).getByRole("listitem");
  await expect(items).toHaveText(["Vim: 0 votes (0%)", "Emacs: 0 votes (0%)", "VS Code: 1 vote (100%)"]);
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
  for (const option of OPTIONS) {
    await expect(page.getByRole("radio", { name: option })).toBeDisabled();
  }
});

test("rejects a second vote from the same visitor on the server", async ({ page }) => {
  await vote(page, "Vim");
  await expect(page.getByText("Thanks for voting")).toBeVisible();
  const res = await page.request.post("/api/votes", { data: { option: "Emacs" } });
  expect(res.status()).toBe(409);
  await page.reload();
  await expect(page.getByRole("list", { name: "Results" }).getByRole("listitem").first()).toHaveText("Vim: 1 vote (100%)");
});

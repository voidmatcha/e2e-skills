import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByRole("radio")).toHaveCount(3);
});

async function vote(page, option) {
  await page.getByRole("radio", { name: option }).check();
  await page.getByRole("button", { name: "Vote" }).click();
}

test("voting shows one result line per option", async ({ page }) => {
  await vote(page, "Vim");
  const items = page.getByRole("list", { name: "Results" }).getByRole("listitem");
  await expect(items).toHaveText(["Vim: 1 vote (100%)", "Emacs: 0 votes (0%)", "VS Code: 0 votes (0%)"]);
});

test("results are hidden until the visitor has voted", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Results" })).toBeHidden();
  await expect(page.getByRole("list", { name: "Results" })).toBeHidden();
  await vote(page, "Emacs");
  await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
});

test("voting without choosing an option does not reveal results", async ({ page }) => {
  await page.getByRole("button", { name: "Vote" }).click();
  await expect(page.getByRole("status")).toHaveText("Pick an option first");
  await expect(page.getByRole("list", { name: "Results" })).toBeHidden();
});

test("after voting the form is disabled and a thanks message shows", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Vote" })).toBeEnabled();
  await vote(page, "VS Code");
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
  for (const radio of await page.getByRole("radio").all()) {
    await expect(radio).toBeDisabled();
  }
});

test("the vote is stored on the server and survives a reload", async ({ page }) => {
  await vote(page, "VS Code");
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");

  await page.reload();
  const items = page.getByRole("list", { name: "Results" }).getByRole("listitem");
  await expect(items).toHaveText(["Vim: 0 votes (0%)", "Emacs: 0 votes (0%)", "VS Code: 1 vote (100%)"]);
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
  for (const radio of await page.getByRole("radio").all()) {
    await expect(radio).toBeDisabled();
  }
});

test("a visitor cannot vote twice via the API", async ({ page }) => {
  await vote(page, "Vim");
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  const res = await page.request.post("/api/votes", { data: { option: "Emacs" } });
  expect(res.status()).toBe(409);
  await page.reload();
  await expect(page.getByRole("list", { name: "Results" }).getByRole("listitem")).toHaveText([
    "Vim: 1 vote (100%)",
    "Emacs: 0 votes (0%)",
    "VS Code: 0 votes (0%)",
  ]);
});

import { expect, test } from "@playwright/test";

const OPTIONS = ["Vim", "Emacs", "VS Code"];

test.beforeEach(async ({ page, request }) => {
  // The app keeps votes in memory; reset so every test starts with zero votes and no voter.
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await page.goto("/");
  // Options are rendered after the initial results fetch; wait for them before interacting.
  await expect(page.getByRole("radio", { name: "Vim" })).toBeVisible();
});

test("hides the results until the visitor has voted", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Vote" })).toBeEnabled();
  await expect(page.getByRole("list", { name: "Results" })).toBeHidden();
  await expect(page.getByText("Thanks for voting")).toBeHidden();
});

test("shows one result line per option after voting", async ({ page }) => {
  const voteRequest = page.waitForRequest(
    (request) => request.method() === "POST" && new URL(request.url()).pathname === "/api/votes",
  );
  await page.getByRole("radio", { name: "Vim" }).check();
  await page.getByRole("button", { name: "Vote" }).click();
  expect((await voteRequest).postDataJSON()).toEqual({ option: "Vim" });

  await expect(page.getByRole("listitem").filter({ hasText: /: \d+ votes?/ })).toHaveCount(OPTIONS.length);
  await expect(page.getByRole("listitem")).toHaveText([
    "Vim: 1 vote (100%)",
    "Emacs: 0 votes (0%)",
    "VS Code: 0 votes (0%)",
  ]);
});

test("disables the form and thanks the visitor after voting", async ({ page }) => {
  await page.getByRole("radio", { name: "Emacs" }).check();
  await page.getByRole("button", { name: "Vote" }).click();

  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
  for (const option of OPTIONS) {
    await expect(page.getByRole("radio", { name: option })).toBeDisabled();
  }
});

test("keeps the vote on the server across a reload", async ({ page }) => {
  await page.getByRole("radio", { name: "VS Code" }).check();
  await page.getByRole("button", { name: "Vote" }).click();
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");

  await page.reload();

  await expect(page.getByRole("listitem")).toHaveText([
    "Vim: 0 votes (0%)",
    "Emacs: 0 votes (0%)",
    "VS Code: 1 vote (100%)",
  ]);
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
  for (const option of OPTIONS) {
    await expect(page.getByRole("radio", { name: option })).toBeDisabled();
  }
});

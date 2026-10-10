import { expect, test } from "@playwright/test";

const OPTIONS = ["Vim", "Emacs", "VS Code"];

test.beforeEach(async ({ page }) => {
  // Disposable state: every test starts from zero votes and a fresh visitor cookie.
  const reset = await page.request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await page.goto("/");
  // Options are rendered after the initial results fetch; wait for them before interacting.
  await expect(page.getByRole("radio", { name: "Vim" })).toBeVisible();
});

const results = (page) => page.getByRole("list", { name: "Results" });

async function vote(page, option) {
  const request = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/votes");
  await page.getByRole("radio", { name: option }).check();
  await page.getByRole("button", { name: "Vote" }).click();
  expect((await request).postDataJSON()).toEqual({ option });
}

test("lists the three options and hides the results before voting", async ({ page }) => {
  for (const option of OPTIONS) {
    await expect(page.getByRole("radio", { name: option })).toBeEnabled();
  }
  await expect(page.getByRole("button", { name: "Vote" })).toBeEnabled();
  await expect(page.getByRole("heading", { name: "Results" })).toBeHidden();
  await expect(results(page)).toBeHidden();
});

test("shows one result line per option after voting", async ({ page }) => {
  await vote(page, "Vim");

  await expect(results(page).getByRole("listitem")).toHaveText([
    "Vim: 1 vote (100%)",
    "Emacs: 0 votes (0%)",
    "VS Code: 0 votes (0%)",
  ]);
});

test("disables the form and thanks the visitor after voting", async ({ page }) => {
  await vote(page, "Emacs");

  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  for (const option of OPTIONS) {
    await expect(page.getByRole("radio", { name: option })).toBeDisabled();
  }
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
});

test("keeps the vote on the server across a reload", async ({ page }) => {
  await vote(page, "VS Code");
  await expect(results(page)).toBeVisible();

  await page.reload();

  await expect(results(page).getByRole("listitem")).toHaveText([
    "Vim: 0 votes (0%)",
    "Emacs: 0 votes (0%)",
    "VS Code: 1 vote (100%)",
  ]);
  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  for (const option of OPTIONS) {
    await expect(page.getByRole("radio", { name: option })).toBeDisabled();
  }
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
});

test("rejects a second vote from the same visitor on the server", async ({ page }) => {
  await vote(page, "Vim");
  await page.reload();
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();

  const second = await page.request.post("/api/votes", { data: { option: "Emacs" } });

  expect(second.status()).toBe(409);
  await page.reload();
  await expect(results(page).getByRole("listitem")).toHaveText([
    "Vim: 1 vote (100%)",
    "Emacs: 0 votes (0%)",
    "VS Code: 0 votes (0%)",
  ]);
});

import { expect, test } from "@playwright/test";

const OPTIONS = ["Vim", "Emacs", "VS Code"];

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBe(true);
  await page.goto("/");
  // The options are rendered after the results fetch, so this is the ready gate.
  await expect(page.getByRole("radio")).toHaveCount(OPTIONS.length);
});

async function vote(page, option) {
  await page.getByRole("radio", { name: option }).check();
  const request = page.waitForRequest((req) => req.url().endsWith("/api/votes") && req.method() === "POST");
  const response = page.waitForResponse((res) => res.url().endsWith("/api/votes") && res.request().method() === "POST");
  await page.getByRole("button", { name: "Vote" }).click();
  expect((await request).postDataJSON()).toEqual({ option });
  expect((await response).status()).toBe(201);
}

test("hides the results until the visitor has voted", async ({ page }) => {
  await expect(page.getByRole("button", { name: "Vote" })).toBeEnabled();
  // The section exists but is hidden, so the role locators below cannot be vacuously absent.
  await expect(page.locator("#pl-results")).toHaveAttribute("hidden", "");
  await expect(page.getByRole("heading", { name: "Results" })).toBeHidden();
  await expect(page.getByRole("list", { name: "Results" })).toBeHidden();
});

test("voting shows one result line per option", async ({ page }) => {
  await vote(page, "Vim");

  const results = page.getByRole("list", { name: "Results" });
  await expect(results.getByRole("listitem")).toHaveText([
    "Vim: 1 vote (100%)",
    "Emacs: 0 votes (0%)",
    "VS Code: 0 votes (0%)",
  ]);
});

test("voting disables the form and thanks the visitor", async ({ page }) => {
  await vote(page, "Emacs");

  await expect(page.getByRole("status")).toHaveText("Thanks for voting");
  await expect(page.getByRole("button", { name: "Vote" })).toBeDisabled();
  for (const option of OPTIONS) {
    await expect(page.getByRole("radio", { name: option })).toBeDisabled();
  }
});

test("the vote is stored on the server and survives a reload", async ({ page }) => {
  await vote(page, "VS Code");

  await page.reload();

  await expect(page.getByRole("list", { name: "Results" }).getByRole("listitem")).toHaveText([
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

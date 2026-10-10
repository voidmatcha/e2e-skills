import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const box = (page) => page.getByLabel("Search the catalog");
const results = (page) => page.getByRole("list", { name: "Results" }).getByRole("listitem");
const status = (page) => page.getByRole("status");
const recent = (page) => page.getByRole("list", { name: "Recent searches" }).getByRole("listitem");

test("lists titles containing the typed text with a result count", async ({ page }) => {
  await box(page).fill("alice");
  await expect(status(page)).toHaveText('1 result for "alice"');
  await expect(results(page)).toHaveText(["Alice in Wonderland"]);

  await box(page).fill("fra");
  await expect(status(page)).toHaveText('1 result for "fra"');
  await expect(results(page)).toHaveText(["Frankenstein"]);

  await box(page).fill("ani");
  await expect(status(page)).toHaveText('1 result for "ani"');
});

test("matches case-insensitively and shows every matching title", async ({ page }) => {
  await box(page).fill("AL");
  await expect(status(page)).toHaveText('4 results for "AL"');
  await expect(results(page)).toHaveText(["Algorithms Unlocked", "Alice in Wonderland", "Animal Farm", "Walden"]);
});

test("shows a message when nothing matches", async ({ page }) => {
  await box(page).fill("zzzz");
  await expect(status(page)).toHaveText('0 results for "zzzz"');
  await expect(results(page)).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeVisible();

  await box(page).fill("dune");
  await expect(results(page)).toHaveText(["Dune"]);
  await expect(page.getByText("No titles match")).toBeHidden();
});

test("typing quickly never leaves results from an earlier, shorter query", async ({ page }) => {
  // one- and two-character queries are slow on the server, longer ones are fast
  await box(page).pressSequentially("alice", { delay: 20 });
  await expect(status(page)).toHaveText('1 result for "alice"');
  // wait past the slow responses of "a" and "al" (700ms each)
  await page.waitForTimeout(1200);
  await expect(box(page)).toHaveValue("alice");
  await expect(status(page)).toHaveText('1 result for "alice"');
  await expect(results(page)).toHaveText(["Alice in Wonderland"]);
});

test("records searches of three or more characters, newest first, without duplicates", async ({ page }) => {
  await box(page).fill("ab");
  await expect(status(page)).toHaveText(/for "ab"/);
  await expect(recent(page)).toHaveCount(0);

  await box(page).fill("dune");
  await expect(results(page)).toHaveText(["Dune"]);
  await box(page).fill("emma");
  await expect(results(page)).toHaveText(["Emma"]);
  await expect(recent(page)).toHaveText(["emma", "dune"]);

  await box(page).fill("dune");
  await expect(results(page)).toHaveText(["Dune"]);
  await expect(recent(page)).toHaveText(["dune", "emma"]);
});

test("recent searches survive a reload and can be run again", async ({ page }) => {
  await box(page).fill("dune");
  await expect(results(page)).toHaveText(["Dune"]);
  await box(page).fill("emma");
  await expect(results(page)).toHaveText(["Emma"]);

  await page.reload();
  await expect(recent(page)).toHaveText(["emma", "dune"]);
  await expect(results(page)).toHaveCount(0);

  await page.getByRole("button", { name: "dune" }).click();
  await expect(box(page)).toHaveValue("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await expect(results(page)).toHaveText(["Dune"]);
  await expect(recent(page)).toHaveText(["dune", "emma"]);
});

test("clearing the box clears the results and the status", async ({ page }) => {
  await box(page).fill("alice");
  await expect(results(page)).toHaveText(["Alice in Wonderland"]);

  await box(page).fill("");
  await expect(results(page)).toHaveCount(0);
  await expect(status(page)).toHaveText("");
  await expect(page.getByText("No titles match")).toBeHidden();
});

test("clearing the box right after typing is not undone by a late response", async ({ page }) => {
  await box(page).fill("al"); // slow query (700ms)
  await box(page).fill("");
  await page.waitForTimeout(1200);
  await expect(box(page)).toHaveValue("");
  await expect(results(page)).toHaveCount(0);
  await expect(status(page)).toHaveText("");
});

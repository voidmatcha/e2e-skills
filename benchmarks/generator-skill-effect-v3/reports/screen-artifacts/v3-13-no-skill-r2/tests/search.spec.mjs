import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
});

const box = (page) => page.getByLabel("Search the catalog");
const items = (page) => page.getByRole("list", { name: "Results" }).getByRole("listitem");
const status = (page) => page.getByRole("status");
const recent = (page) => page.getByRole("list", { name: "Recent searches" }).getByRole("listitem");

test("lists matching titles and a plural status", async ({ page }) => {
  await box(page).fill("Alice");
  await expect(status(page)).toHaveText('1 result for "Alice"');
  await expect(items(page)).toHaveText(["Alice in Wonderland"]);

  await box(page).fill("an");
  await expect(status(page)).toHaveText(/^\d+ results for "an"$/);
  const titles = await items(page).allTextContents();
  expect(titles.length).toBeGreaterThan(1);
  for (const t of titles) expect(t.toLowerCase()).toContain("an");
});

test("matching is case-insensitive", async ({ page }) => {
  await box(page).fill("hobbit");
  await expect(items(page)).toHaveText(["The Hobbit"]);
});

test("shows a message when nothing matches", async ({ page }) => {
  await box(page).fill("zzzz");
  await expect(page.getByText("No titles match")).toBeVisible();
  await expect(status(page)).toHaveText('0 results for "zzzz"');
  await expect(items(page)).toHaveCount(0);

  await box(page).fill("dune");
  await expect(page.getByText("No titles match")).toBeHidden();
  await expect(items(page)).toHaveText(["Dune"]);
});

test("typing quickly never leaves results from an earlier, shorter query", async ({ page }) => {
  // "a"/"al" are slow responses, "alg" is fast: the slow ones must not overwrite it
  await box(page).pressSequentially("alg", { delay: 20 });
  await expect(status(page)).toHaveText('1 result for "alg"');
  await expect(items(page)).toHaveText(["Algorithms Unlocked"]);

  // stay stable past the slow responses (700ms) for the earlier queries
  await page.waitForTimeout(1200);
  await expect(status(page)).toHaveText('1 result for "alg"');
  await expect(items(page)).toHaveText(["Algorithms Unlocked"]);
});

test("a slow short query that is the final text still shows its results", async ({ page }) => {
  await box(page).fill("du");
  await expect(status(page)).toHaveText('1 result for "du"');
  await expect(items(page)).toHaveText(["Dune"]);
});

test("records searches of three or more characters, newest first, without duplicates", async ({ page }) => {
  await box(page).fill("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await box(page).fill("emma");
  await expect(status(page)).toHaveText('1 result for "emma"');
  await box(page).fill("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await expect(recent(page)).toHaveText(["dune", "emma"]);
});

test("does not record searches shorter than three characters", async ({ page }) => {
  await box(page).fill("du");
  await expect(status(page)).toHaveText('1 result for "du"');
  await expect(recent(page)).toHaveCount(0);
});

test("recent searches survive a reload", async ({ page }) => {
  await box(page).fill("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await box(page).fill("emma");
  await expect(status(page)).toHaveText('1 result for "emma"');

  await page.reload();
  await expect(recent(page)).toHaveText(["emma", "dune"]);
});

test("clicking a recent search runs it again", async ({ page }) => {
  await box(page).fill("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await box(page).fill("emma");
  await expect(status(page)).toHaveText('1 result for "emma"');

  await page.getByRole("button", { name: "dune" }).click();
  await expect(box(page)).toHaveValue("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await expect(items(page)).toHaveText(["Dune"]);
  await expect(recent(page)).toHaveText(["dune", "emma"]);
});

test("clearing the box clears results and status", async ({ page }) => {
  await box(page).fill("dune");
  await expect(items(page)).toHaveText(["Dune"]);

  await box(page).fill("");
  await expect(items(page)).toHaveCount(0);
  await expect(status(page)).toHaveText("");
  await expect(page.getByText("No titles match")).toBeHidden();
});

test("clearing while a slow search is in flight is not overwritten", async ({ page }) => {
  await box(page).fill("du"); // slow response (~700ms)
  await box(page).fill("");
  await page.waitForTimeout(1200);
  await expect(items(page)).toHaveCount(0);
  await expect(status(page)).toHaveText("");
});

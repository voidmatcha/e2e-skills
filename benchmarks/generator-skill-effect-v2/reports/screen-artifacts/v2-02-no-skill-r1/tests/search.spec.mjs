import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const box = (page) => page.getByLabel("Search the catalog");
const status = (page) => page.getByRole("status");
const results = (page) => page.getByRole("list", { name: "Results" }).getByRole("listitem");
const recent = (page) => page.getByRole("list", { name: "Recent searches" }).getByRole("listitem");

test("shows matching titles and a plural status line", async ({ page }) => {
  await box(page).fill("an");
  await expect(status(page)).toHaveText('5 results for "an"');
  await expect(results(page)).toHaveText(["Alice in Wonderland", "Animal Farm", "Frankenstein", "Jane Eyre", "Neuromancer"]);
});

test("matches titles case-insensitively with a singular status", async ({ page }) => {
  await box(page).fill("hobbit");
  await expect(status(page)).toHaveText('1 result for "hobbit"');
  await expect(results(page)).toHaveText(["The Hobbit"]);
});

test("shows a message when nothing matches", async ({ page }) => {
  await box(page).fill("zzzz");
  await expect(status(page)).toHaveText('0 results for "zzzz"');
  await expect(results(page)).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeVisible();
});

test("fast typing ends with results for the full query only", async ({ page }) => {
  await box(page).pressSequentially("alice", { delay: 0 });
  await expect(status(page)).toHaveText('1 result for "alice"');
  await expect(results(page)).toHaveText(["Alice in Wonderland"]);
  // let the slow responses for "a" and "al" arrive; they must not overwrite
  await page.waitForTimeout(1200);
  await expect(status(page)).toHaveText('1 result for "alice"');
  await expect(results(page)).toHaveText(["Alice in Wonderland"]);
});

test("a slow short query does not replace the results of a longer one", async ({ page }) => {
  await box(page).fill("a");
  await box(page).fill("ali");
  await page.waitForTimeout(1200);
  await expect(status(page)).toHaveText('1 result for "ali"');
  await expect(results(page)).toHaveText(["Alice in Wonderland"]);
});

test("records searches of three or more characters, newest first, without duplicates", async ({ page }) => {
  for (const q of ["dune", "ham", "dune"]) {
    await box(page).fill(q);
    await expect(status(page)).toContainText(`for "${q}"`);
  }
  await expect(recent(page)).toHaveText(["dune", "ham"]);
});

test("does not record searches shorter than three characters", async ({ page }) => {
  await box(page).fill("em");
  await expect(status(page)).toContainText('for "em"');
  await expect(recent(page)).toHaveCount(0);
});

test("recent searches survive a reload", async ({ page }) => {
  await box(page).fill("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await page.reload();
  await expect(recent(page)).toHaveText(["dune"]);
});

test("clicking a recent search runs it again", async ({ page }) => {
  for (const q of ["dune", "hobbit"]) {
    await box(page).fill(q);
    await expect(status(page)).toContainText(`for "${q}"`);
  }
  await page.reload();
  await page.getByRole("button", { name: "dune" }).click();
  await expect(box(page)).toHaveValue("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await expect(results(page)).toHaveText(["Dune"]);
  await expect(recent(page)).toHaveText(["dune", "hobbit"]);
});

test("clearing the box clears results and status", async ({ page }) => {
  await box(page).fill("dune");
  await expect(results(page)).toHaveCount(1);
  await box(page).fill("");
  await expect(results(page)).toHaveCount(0);
  await expect(status(page)).toHaveText("");
  await expect(page.getByText("No titles match")).toBeHidden();
});

test("clearing while a slow search is in flight stays cleared", async ({ page }) => {
  await box(page).fill("a");
  await box(page).fill("");
  await page.waitForTimeout(1200);
  await expect(results(page)).toHaveCount(0);
  await expect(status(page)).toHaveText("");
});

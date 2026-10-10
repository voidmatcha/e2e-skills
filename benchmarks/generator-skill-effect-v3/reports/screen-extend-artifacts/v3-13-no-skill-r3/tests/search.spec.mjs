import { expect, test } from "@playwright/test";

const box = (page) => page.getByLabel("Search the catalog");
const results = (page) => page.getByRole("list", { name: "Results" });
const recent = (page) => page.getByRole("list", { name: "Recent searches" });
const status = (page) => page.getByRole("status");

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("lists titles containing the typed text", async ({ page }) => {
  await box(page).fill("an");
  await expect(status(page)).toHaveText('5 results for "an"');
  await expect(results(page).getByRole("listitem")).toHaveText([
    "Alice in Wonderland", "Animal Farm", "Frankenstein", "Jane Eyre", "Neuromancer",
  ]);
});

test("matches case-insensitively and uses singular for one result", async ({ page }) => {
  await box(page).fill("DUNE");
  await expect(status(page)).toHaveText('1 result for "DUNE"');
  await expect(results(page).getByRole("listitem")).toHaveText(["Dune"]);
});

test("shows a message when nothing matches", async ({ page }) => {
  await box(page).fill("zzzz");
  await expect(page.getByText("No titles match")).toBeVisible();
  await expect(status(page)).toHaveText('0 results for "zzzz"');
  await expect(results(page).getByRole("listitem")).toHaveCount(0);
});

test("fast typing never leaves results from an earlier, shorter query", async ({ page }) => {
  // one- and two-character queries are slow on the server; the longer one is fast
  await box(page).pressSequentially("hobbit", { delay: 20 });
  await expect(status(page)).toHaveText('1 result for "hobbit"');
  await expect(results(page).getByRole("listitem")).toHaveText(["The Hobbit"]);
  // wait past the slow responses' latency; the list must still match the box
  await page.waitForTimeout(1200);
  await expect(status(page)).toHaveText('1 result for "hobbit"');
  await expect(results(page).getByRole("listitem")).toHaveText(["The Hobbit"]);
});

test("a slow short query does not overwrite a quickly typed longer one", async ({ page }) => {
  await box(page).fill("a");
  await box(page).fill("alice");
  await page.waitForTimeout(1200);
  await expect(status(page)).toHaveText('1 result for "alice"');
  await expect(results(page).getByRole("listitem")).toHaveText(["Alice in Wonderland"]);
});

test("searches of three or more characters are recorded newest first without duplicates", async ({ page }) => {
  for (const q of ["dune", "emma", "hamlet", "dune"]) {
    await box(page).fill(q);
    await expect(status(page)).toContainText(`for "${q}"`);
  }
  await expect(recent(page).getByRole("listitem")).toHaveText(["dune", "hamlet", "emma"]);
});

test("searches shorter than three characters are not recorded", async ({ page }) => {
  await box(page).fill("em");
  await expect(status(page)).toHaveText('1 result for "em"');
  await expect(recent(page).getByRole("listitem")).toHaveCount(0);
});

test("recent searches survive a reload", async ({ page }) => {
  await box(page).fill("emma");
  await expect(status(page)).toHaveText('1 result for "emma"');
  await box(page).fill("walden");
  await expect(status(page)).toHaveText('1 result for "walden"');
  await page.reload();
  await expect(recent(page).getByRole("listitem")).toHaveText(["walden", "emma"]);
});

test("clicking a recent search runs it again", async ({ page }) => {
  await box(page).fill("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await box(page).fill("zzzz");
  await expect(status(page)).toHaveText('0 results for "zzzz"');
  await recent(page).getByRole("button", { name: "dune" }).click();
  await expect(box(page)).toHaveValue("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await expect(results(page).getByRole("listitem")).toHaveText(["Dune"]);
});

test("clearing the box clears results and status", async ({ page }) => {
  await box(page).fill("dune");
  await expect(results(page).getByRole("listitem")).toHaveText(["Dune"]);
  await box(page).fill("");
  await expect(results(page).getByRole("listitem")).toHaveCount(0);
  await expect(status(page)).toHaveText("");
  await expect(page.getByText("No titles match")).toBeHidden();
});

test("clearing while a slow search is in flight stays cleared", async ({ page }) => {
  await box(page).fill("a");
  await box(page).fill("");
  await page.waitForTimeout(1200);
  await expect(results(page).getByRole("listitem")).toHaveCount(0);
  await expect(status(page)).toHaveText("");
});

import { expect, test } from "@playwright/test";

const box = (page) => page.getByLabel("Search the catalog");
const results = (page) => page.getByRole("list", { name: "Results" }).getByRole("listitem");
const recent = (page) => page.getByRole("list", { name: "Recent searches" }).getByRole("listitem");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("filters titles and reports the count", async ({ page }) => {
  await box(page).fill("Alice");
  await expect(results(page)).toHaveText(["Alice in Wonderland"]);
  await expect(page.getByRole("status")).toHaveText('1 result for "Alice"');
  await box(page).fill("zzz");
  await expect(results(page)).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeVisible();
  await expect(page.getByRole("status")).toHaveText('0 results for "zzz"');
});

test("fast typing never shows results of a shorter earlier query", async ({ page }) => {
  await box(page).pressSequentially("Dune", { delay: 30 });
  await expect(page.getByRole("status")).toHaveText('1 result for "Dune"');
  await expect(results(page)).toHaveText(["Dune"]);
  // the slow one-letter responses arrive after this point; the list must still match the box
  await page.waitForTimeout(1200);
  await expect(results(page)).toHaveText(["Dune"]);
  await expect(page.getByRole("status")).toHaveText('1 result for "Dune"');
});

test("recent searches are kept newest first without duplicates and survive a reload", async ({ page }) => {
  await box(page).fill("Emma");
  await expect(page.getByRole("status")).toHaveText('1 result for "Emma"');
  await box(page).fill("Dune");
  await expect(page.getByRole("status")).toHaveText('1 result for "Dune"');
  await box(page).fill("Emma");
  await expect(page.getByRole("status")).toHaveText('1 result for "Emma"');
  await expect(recent(page)).toHaveText(["Emma", "Dune"]);
  await page.reload();
  await expect(recent(page)).toHaveText(["Emma", "Dune"]);
});

test("clicking a recent search runs it again", async ({ page }) => {
  await box(page).fill("Hamlet");
  await expect(page.getByRole("status")).toHaveText('1 result for "Hamlet"');
  await box(page).fill("");
  await expect(results(page)).toHaveCount(0);
  await expect(page.getByRole("status")).toHaveText("");
  await page.getByRole("list", { name: "Recent searches" }).getByRole("button", { name: "Hamlet" }).click();
  await expect(box(page)).toHaveValue("Hamlet");
  await expect(results(page)).toHaveText(["Hamlet"]);
});

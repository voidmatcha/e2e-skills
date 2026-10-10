import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const box = (page) => page.getByLabel("Search the catalog");
const results = (page) => page.getByRole("list", { name: "Results" }).getByRole("listitem");
const status = (page) => page.getByRole("status");
const recent = (page) => page.getByRole("list", { name: "Recent searches" }).getByRole("listitem");

test("lists matching titles and a plural status", async ({ page }) => {
  await box(page).fill("alg");
  await expect(status(page)).toHaveText('1 result for "alg"');
  await expect(results(page)).toHaveText(["Algorithms Unlocked"]);

  await box(page).fill("an");
  await expect(status(page)).toHaveText('5 results for "an"');
  await expect(results(page)).toHaveText([
    "Alice in Wonderland",
    "Animal Farm",
    "Frankenstein",
    "Jane Eyre",
    "Neuromancer",
  ]);
});

test("shows a singular status for one match", async ({ page }) => {
  await box(page).fill("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await expect(results(page)).toHaveText(["Dune"]);
});

test("shows a message when nothing matches", async ({ page }) => {
  await box(page).fill("zzzz");
  await expect(status(page)).toHaveText('0 results for "zzzz"');
  await expect(page.getByText("No titles match")).toBeVisible();
  await expect(results(page)).toHaveCount(0);
});

test("fast typing never leaves results from an earlier, shorter query", async ({ page }) => {
  // "a" and "ab" are slow server-side; "abc" is fast and would overtake them
  await box(page).pressSequentially("hob", { delay: 0 });
  await expect(status(page)).toHaveText('1 result for "hob"');
  await expect(results(page)).toHaveText(["The Hobbit"]);
  // wait past the slow responses for "h" and "ho" and check nothing overwrote
  await page.waitForTimeout(1200);
  await expect(status(page)).toHaveText('1 result for "hob"');
  await expect(results(page)).toHaveText(["The Hobbit"]);
  await expect(box(page)).toHaveValue("hob");
});

test("records searches of three or more characters, newest first, without duplicates", async ({ page }) => {
  await box(page).fill("ab");
  await expect(status(page)).toHaveText('0 results for "ab"');
  await expect(recent(page)).toHaveCount(0);

  await box(page).fill("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await box(page).fill("emma");
  await expect(status(page)).toHaveText('1 result for "emma"');
  await box(page).fill("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await expect(recent(page)).toHaveText(["dune", "emma"]);
});

test("recent searches survive a reload and rerun when clicked", async ({ page }) => {
  await box(page).fill("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await box(page).fill("emma");
  await expect(status(page)).toHaveText('1 result for "emma"');

  await page.reload();
  await expect(recent(page)).toHaveText(["emma", "dune"]);

  await page.getByRole("button", { name: "dune" }).click();
  await expect(box(page)).toHaveValue("dune");
  await expect(status(page)).toHaveText('1 result for "dune"');
  await expect(results(page)).toHaveText(["Dune"]);
  await expect(recent(page)).toHaveText(["dune", "emma"]);
});

test("clearing the box clears results and status", async ({ page }) => {
  await box(page).fill("dune");
  await expect(results(page)).toHaveCount(1);
  await box(page).fill("");
  await expect(results(page)).toHaveCount(0);
  await expect(status(page)).toHaveText("");
  await expect(page.getByText("No titles match")).toBeHidden();
});

test("clearing while a slow search is pending leaves the page empty", async ({ page }) => {
  await box(page).fill("a");
  await box(page).fill("");
  await page.waitForTimeout(1200);
  await expect(results(page)).toHaveCount(0);
  await expect(status(page)).toHaveText("");
});

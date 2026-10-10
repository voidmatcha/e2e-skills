import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

const queryBox = (page) => page.getByLabel("Search the catalog");
const statusLine = (page) => page.getByRole("status");
const resultsList = (page) => page.getByRole("list", { name: "Results" });
const recentList = (page) => page.getByRole("list", { name: "Recent searches" });

async function expectResults(page, titles) {
  await expect(resultsList(page).locator("li")).toHaveText(titles);
}

test("shows matching titles and result counts while typing", async ({ page }) => {
  await queryBox(page).fill("dun");

  await expect(statusLine(page)).toHaveText('1 result for "dun"');
  await expectResults(page, ["Dune"]);

  await queryBox(page).fill("an");

  await expect(statusLine(page)).toHaveText('5 results for "an"');
  await expectResults(page, [
    "Alice in Wonderland",
    "Animal Farm",
    "Frankenstein",
    "Jane Eyre",
    "Neuromancer",
  ]);
});

test("shows the empty state when no titles match", async ({ page }) => {
  await queryBox(page).fill("zzzz");

  await expect(statusLine(page)).toHaveText('0 results for "zzzz"');
  await expect(page.getByText("No titles match")).toBeVisible();
  await expectResults(page, []);
});

test("keeps the results synced to the current input during fast typing", async ({ page }) => {
  await queryBox(page).fill("a");
  await queryBox(page).fill("dun");

  await expect(statusLine(page)).toHaveText('1 result for "dun"');
  await expectResults(page, ["Dune"]);

  await page.waitForTimeout(800);
  await expect(queryBox(page)).toHaveValue("dun");
  await expect(statusLine(page)).toHaveText('1 result for "dun"');
  await expectResults(page, ["Dune"]);
});

test("stores recent searches newest first without duplicates and reruns them after reload", async ({ page }) => {
  await queryBox(page).fill("ham");
  await expect(statusLine(page)).toHaveText('1 result for "ham"');

  await queryBox(page).fill("dun");
  await expect(statusLine(page)).toHaveText('1 result for "dun"');

  await queryBox(page).fill("du");
  await expect(statusLine(page)).toHaveText('1 result for "du"');

  await queryBox(page).fill("ham");
  await expect(statusLine(page)).toHaveText('1 result for "ham"');
  await expect(recentList(page).getByRole("button")).toHaveText(["ham", "dun"]);

  await page.reload();
  await expect(recentList(page).getByRole("button")).toHaveText(["ham", "dun"]);

  await recentList(page).getByRole("button", { name: "dun" }).click();
  await expect(queryBox(page)).toHaveValue("dun");
  await expect(statusLine(page)).toHaveText('1 result for "dun"');
  await expectResults(page, ["Dune"]);
});

test("clearing the query clears the results and status", async ({ page }) => {
  await queryBox(page).fill("ali");
  await expect(statusLine(page)).toHaveText('1 result for "ali"');
  await expectResults(page, ["Alice in Wonderland"]);

  await queryBox(page).fill("");

  await expect(statusLine(page)).toHaveText("");
  await expect(resultsList(page).locator("li")).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeHidden();
});

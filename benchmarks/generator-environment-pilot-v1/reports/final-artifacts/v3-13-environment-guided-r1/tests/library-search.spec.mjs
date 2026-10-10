import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("updates results and status as the reader searches", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const results = page.getByRole("list", { name: "Results", exact: true });

  await searchBox.fill("al");
  await expect(status).toHaveText('4 results for "al"');
  await expect(results.getByRole("listitem")).toHaveText([
    "Algorithms Unlocked",
    "Alice in Wonderland",
    "Animal Farm",
    "Walden",
  ]);

  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await expect(results.getByRole("listitem")).toHaveText(["Dune"]);
});

test("shows the empty state when no titles match", async ({ page }) => {
  await page.getByLabel("Search the catalog").fill("zzx");

  await expect(page.getByRole("status")).toHaveText('0 results for "zzx"');
  await expect(page.getByText("No titles match")).toBeVisible();
});

test("keeps the list matched to the current fast-typed query", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const results = page.getByRole("list", { name: "Results", exact: true });
  const slowShortSearch = page.waitForResponse((response) =>
    response.url().includes("/api/search?q=a") && response.status() === 200
  );

  await searchBox.fill("a");
  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await expect(results.getByRole("listitem")).toHaveText(["Dune"]);

  await slowShortSearch;
  await expect(searchBox).toHaveValue("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await expect(results.getByRole("listitem")).toHaveText(["Dune"]);
});

test("stores recent searches, preserves them after reload, and replays them when clicked", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const recentSearches = page.getByRole("list", { name: "Recent searches", exact: true });

  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');

  await searchBox.fill("alice");
  await expect(status).toHaveText('1 result for "alice"');

  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await expect(recentSearches.getByRole("button")).toHaveText(["dune", "alice"]);

  await page.reload();
  await expect(recentSearches.getByRole("button")).toHaveText(["dune", "alice"]);

  await recentSearches.getByRole("button", { name: "alice" }).click();
  await expect(searchBox).toHaveValue("alice");
  await expect(status).toHaveText('1 result for "alice"');
  await expect(page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem")).toHaveText([
    "Alice in Wonderland",
  ]);
});

test("clearing the search box clears the results and status", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const results = page.getByRole("list", { name: "Results", exact: true });

  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await expect(results.getByRole("listitem")).toHaveText(["Dune"]);

  await searchBox.fill("");
  await expect(status).toBeEmpty();
  await expect(results.getByRole("listitem")).toHaveCount(0);
});

import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("shows matching titles and the singular result status while typing", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");

  await searchBox.fill("dune");

  await expect(page.getByRole("status")).toHaveText('1 result for "dune"');
  await expect(results).toHaveText(["Dune"]);
});

test("shows matching titles and the plural result status while typing", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");

  await searchBox.fill("an");

  await expect(page.getByRole("status")).toHaveText('5 results for "an"');
  await expect(results).toHaveText([
    "Alice in Wonderland",
    "Animal Farm",
    "Frankenstein",
    "Jane Eyre",
    "Neuromancer",
  ]);
});

test("shows the empty state when no titles match", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");

  await searchBox.fill("zzzz");

  await expect(page.getByText("No titles match")).toBeVisible();
  await expect(page.getByRole("status")).toHaveText('0 results for "zzzz"');
  await expect(page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem")).toHaveCount(0);
});

test("keeps quick typing results aligned with the current query", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");
  const slowShortQuery = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/search" && url.searchParams.get("q") === "al";
  });
  const fastCurrentQuery = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/search" && url.searchParams.get("q") === "alice";
  });

  await searchBox.fill("al");
  await searchBox.fill("alice");
  await fastCurrentQuery;
  await slowShortQuery;

  await expect(searchBox).toHaveValue("alice");
  await expect(page.getByRole("status")).toHaveText('1 result for "alice"');
  await expect(results).toHaveText(["Alice in Wonderland"]);
  await expect(results).not.toContainText("Algorithms Unlocked");
});

test("stores recent searches newest first without duplicates and runs one again after reload", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const recent = page.getByRole("list", { name: "Recent searches", exact: true }).getByRole("button");
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");
  const waitForSearch = (query) => page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET"
      && url.pathname === "/api/search"
      && url.searchParams.get("q") === query;
  });

  const firstDuneSearch = waitForSearch("dune");
  await searchBox.fill("dune");
  await firstDuneSearch;
  await expect(page.getByRole("status")).toHaveText('1 result for "dune"');
  const aliceSearch = waitForSearch("alice");
  await searchBox.fill("alice");
  await aliceSearch;
  await expect(page.getByRole("status")).toHaveText('1 result for "alice"');
  const secondDuneSearch = waitForSearch("dune");
  await searchBox.fill("dune");
  await secondDuneSearch;
  await expect(page.getByRole("status")).toHaveText('1 result for "dune"');

  await expect(recent).toHaveText(["dune", "alice"]);

  await page.reload();
  await expect(recent).toHaveText(["dune", "alice"]);

  const rerunAliceSearch = waitForSearch("alice");
  await page.getByRole("button", { name: "alice", exact: true }).click();
  await rerunAliceSearch;

  await expect(searchBox).toHaveValue("alice");
  await expect(page.getByRole("status")).toHaveText('1 result for "alice"');
  await expect(results).toHaveText(["Alice in Wonderland"]);
});

test("clearing the box clears the results and status", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");

  await searchBox.fill("dune");
  await expect(page.getByRole("status")).toHaveText('1 result for "dune"');

  await searchBox.fill("");

  await expect(page.getByRole("status")).toHaveText("");
  await expect(results).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeHidden();
});

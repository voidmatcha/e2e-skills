import { expect, test } from "@playwright/test";

const waitForSearch = (page, query) =>
  page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/search" && url.searchParams.get("q") === query;
  });

const searchFor = async (page, query) => {
  const response = waitForSearch(page, query);
  await page.getByLabel("Search the catalog", { exact: true }).fill(query);
  await response;
};

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("filters titles as the reader types and reports the result count", async ({ page }) => {
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");

  await searchFor(page, "an");

  await expect(page.getByRole("status")).toHaveText('5 results for "an"');
  await expect(results).toHaveText([
    "Alice in Wonderland",
    "Animal Farm",
    "Frankenstein",
    "Jane Eyre",
    "Neuromancer",
  ]);

  await searchFor(page, "hob");

  await expect(page.getByRole("status")).toHaveText('1 result for "hob"');
  await expect(results).toHaveText(["The Hobbit"]);
});

test("shows the empty result state when no titles match", async ({ page }) => {
  await searchFor(page, "zzzz");

  await expect(page.getByRole("status")).toHaveText('0 results for "zzzz"');
  await expect(page.getByText("No titles match")).toBeVisible();
  await expect(page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem")).toHaveCount(0);
});

test("keeps the list aligned to the latest query when typing quickly", async ({ page }) => {
  const slowSearch = waitForSearch(page, "a");
  const fastSearch = waitForSearch(page, "dune");

  await page.getByLabel("Search the catalog", { exact: true }).fill("a");
  await page.getByLabel("Search the catalog", { exact: true }).fill("dune");
  await Promise.all([slowSearch, fastSearch]);

  await expect(page.getByLabel("Search the catalog", { exact: true })).toHaveValue("dune");
  await expect(page.getByRole("status")).toHaveText('1 result for "dune"');
  await expect(page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem")).toHaveText(["Dune"]);
});

test("stores recent searches newest first without duplicates and reruns them after reload", async ({ page }) => {
  const recent = page.getByRole("list", { name: "Recent searches", exact: true }).getByRole("listitem");

  await searchFor(page, "hob");
  await searchFor(page, "dune");
  await searchFor(page, "hob");

  await expect(recent).toHaveText(["hob", "dune"]);

  await page.reload();
  await expect(recent).toHaveText(["hob", "dune"]);

  const response = waitForSearch(page, "dune");
  await page.getByRole("button", { name: "dune", exact: true }).click();
  await response;

  await expect(page.getByLabel("Search the catalog", { exact: true })).toHaveValue("dune");
  await expect(page.getByRole("status")).toHaveText('1 result for "dune"');
  await expect(page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem")).toHaveText(["Dune"]);
});

test("clearing the search box clears the status and results", async ({ page }) => {
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");

  await searchFor(page, "hob");
  await page.getByLabel("Search the catalog", { exact: true }).fill("");

  await expect(page.getByRole("status")).toHaveText("");
  await expect(results).toHaveCount(0);
});

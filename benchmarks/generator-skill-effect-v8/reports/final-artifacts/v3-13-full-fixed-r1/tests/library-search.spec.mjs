import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("filters titles and reports the matching count", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");

  await searchBox.fill("an");

  await expect(status).toHaveText('5 results for "an"');
  await expect(results).toHaveText([
    "Alice in Wonderland",
    "Animal Farm",
    "Frankenstein",
    "Jane Eyre",
    "Neuromancer",
  ]);

  await searchBox.fill("dune");

  await expect(status).toHaveText('1 result for "dune"');
  await expect(results).toHaveText(["Dune"]);
});

test("shows the empty state when no titles match", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");

  await searchBox.fill("dune");
  await expect(results).toHaveText(["Dune"]);

  await searchBox.fill("zzzz");

  await expect(page.getByRole("status")).toHaveText('0 results for "zzzz"');
  await expect(results).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeVisible();
});

test("keeps quick typing on the current query results", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");
  const slowSearch = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/search" && url.searchParams.get("q") === "an";
  });

  await searchBox.fill("an");
  await searchBox.fill("dune");

  await expect(status).toHaveText('1 result for "dune"');
  await slowSearch;
  await expect(status).toHaveText('1 result for "dune"');
  await expect(results).toHaveText(["Dune"]);
});

test("persists recent searches and reruns one from the list", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");
  const recentSearches = page
    .getByRole("list", { name: "Recent searches", exact: true })
    .getByRole("button");

  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await searchBox.fill("hamlet");
  await expect(status).toHaveText('1 result for "hamlet"');
  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');

  await expect(recentSearches).toHaveText(["dune", "hamlet"]);

  await page.reload();
  await expect(recentSearches).toHaveText(["dune", "hamlet"]);

  await page.getByRole("button", { name: "hamlet", exact: true }).click();

  await expect(searchBox).toHaveValue("hamlet");
  await expect(status).toHaveText('1 result for "hamlet"');
  await expect(results).toHaveText(["Hamlet"]);
});

test("clearing the box clears the results and status", async ({ page }) => {
  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const results = page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");

  await searchBox.fill("zzzz");
  await expect(page.getByText("No titles match")).toBeVisible();

  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await expect(results).toHaveText(["Dune"]);
  await expect(page.getByText("No titles match")).toBeHidden();

  await searchBox.fill("");

  await expect(status).toHaveText("");
  await expect(results).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeHidden();
});

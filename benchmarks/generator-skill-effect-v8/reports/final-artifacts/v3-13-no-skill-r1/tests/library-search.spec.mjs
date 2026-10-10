import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("filters titles as the reader types and reports the result count", async ({ page }) => {
  await page.goto("/");

  const search = page.getByLabel("Search the catalog");
  const results = page.getByRole("list", { name: "Results" });
  const status = page.locator("#ls-status");

  await search.fill("dune");

  await expect(status).toHaveText('1 result for "dune"');
  await expect(results).toHaveText("Dune");
  await expect(page.getByText("No titles match")).toBeHidden();

  await search.fill("wo");

  await expect(status).toHaveText('2 results for "wo"');
  await expect(results.getByRole("listitem")).toHaveText(["Alice in Wonderland", "Brave New World"]);
});

test("shows an empty state when no titles match", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Search the catalog").fill("xyz");

  await expect(page.locator("#ls-status")).toHaveText('0 results for "xyz"');
  await expect(page.getByRole("list", { name: "Results" }).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeVisible();
});

test("keeps the results matched to the current query when typing quickly", async ({ page }) => {
  await page.goto("/");

  const search = page.getByLabel("Search the catalog");
  const results = page.getByRole("list", { name: "Results" });
  const status = page.locator("#ls-status");

  await search.fill("a");
  await search.fill("dune");

  await expect(status).toHaveText('1 result for "dune"');
  await expect(results).toHaveText("Dune");

  await page.waitForTimeout(750);

  await expect(search).toHaveValue("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await expect(results).toHaveText("Dune");
  await expect(results.getByText("Animal Farm")).toHaveCount(0);
});

test("stores recent searches newest first, without duplicates, across reloads", async ({ page }) => {
  await page.goto("/");

  const search = page.getByLabel("Search the catalog");
  const recent = page.getByRole("list", { name: "Recent searches" });

  await search.fill("alice");
  await expect(page.locator("#ls-status")).toHaveText('1 result for "alice"');

  await search.fill("dune");
  await expect(page.locator("#ls-status")).toHaveText('1 result for "dune"');

  await search.fill("alice");
  await expect(page.locator("#ls-status")).toHaveText('1 result for "alice"');

  await expect(recent.getByRole("button")).toHaveText(["alice", "dune"]);

  await page.reload();
  await expect(recent.getByRole("button")).toHaveText(["alice", "dune"]);

  await recent.getByRole("button", { name: "dune" }).click();

  await expect(search).toHaveValue("dune");
  await expect(page.locator("#ls-status")).toHaveText('1 result for "dune"');
  await expect(page.getByRole("list", { name: "Results" })).toHaveText("Dune");
});

test("clearing the search box clears the results and status", async ({ page }) => {
  await page.goto("/");

  const search = page.getByLabel("Search the catalog");
  const results = page.getByRole("list", { name: "Results" });
  const status = page.locator("#ls-status");

  await search.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');

  await search.clear();

  await expect(status).toBeEmpty();
  await expect(results.getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeHidden();
});

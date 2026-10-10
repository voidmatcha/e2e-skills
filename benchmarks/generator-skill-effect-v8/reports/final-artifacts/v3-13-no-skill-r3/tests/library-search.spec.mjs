import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("filters titles while typing and handles empty results", async ({ page }) => {
  await page.goto("/");

  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const results = page.getByRole("list", { name: "Results" });

  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await expect(results.getByRole("listitem")).toHaveText(["Dune"]);

  await searchBox.fill("an");
  await expect(status).toHaveText('5 results for "an"');
  await expect(results.getByRole("listitem")).toHaveText([
    "Alice in Wonderland",
    "Animal Farm",
    "Frankenstein",
    "Jane Eyre",
    "Neuromancer",
  ]);

  await searchBox.fill("zzzz");
  await expect(status).toHaveText('0 results for "zzzz"');
  await expect(results.getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeVisible();
});

test("keeps results aligned with the current query when responses return out of order", async ({ page }) => {
  await page.goto("/");

  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const results = page.getByRole("list", { name: "Results" });

  await searchBox.fill("a");
  await searchBox.fill("ali");

  await expect(status).toHaveText('1 result for "ali"');
  await expect(results.getByRole("listitem")).toHaveText(["Alice in Wonderland"]);

  await page.waitForTimeout(750);
  await expect(searchBox).toHaveValue("ali");
  await expect(status).toHaveText('1 result for "ali"');
  await expect(results.getByRole("listitem")).toHaveText(["Alice in Wonderland"]);
});

test("stores recent searches, preserves them after reload, and re-runs them from the list", async ({ page }) => {
  await page.goto("/");

  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const recent = page.getByRole("list", { name: "Recent searches" });

  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await searchBox.fill("em");
  await expect(status).toHaveText('1 result for "em"');
  await searchBox.fill("emma");
  await expect(status).toHaveText('1 result for "emma"');
  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');

  await expect(recent.getByRole("button")).toHaveText(["dune", "emma"]);

  await page.reload();
  await expect(recent.getByRole("button")).toHaveText(["dune", "emma"]);

  await recent.getByRole("button", { name: "emma" }).click();
  await expect(searchBox).toHaveValue("emma");
  await expect(status).toHaveText('1 result for "emma"');
  await expect(page.getByRole("list", { name: "Results" }).getByRole("listitem")).toHaveText(["Emma"]);
  await expect(recent.getByRole("button")).toHaveText(["emma", "dune"]);
});

test("clearing the search box clears the results and status", async ({ page }) => {
  await page.goto("/");

  const searchBox = page.getByLabel("Search the catalog");
  const status = page.getByRole("status");
  const results = page.getByRole("list", { name: "Results" });

  await searchBox.fill("dune");
  await expect(status).toHaveText('1 result for "dune"');
  await expect(results.getByRole("listitem")).toHaveText(["Dune"]);

  await searchBox.fill("");
  await expect(status).toBeEmpty();
  await expect(results.getByRole("listitem")).toHaveCount(0);
  await expect(page.getByText("No titles match")).toBeHidden();
});

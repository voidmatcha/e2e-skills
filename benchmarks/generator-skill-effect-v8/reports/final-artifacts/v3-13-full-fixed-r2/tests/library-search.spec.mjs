import { expect, test } from "@playwright/test";

const queryInput = (page) => page.getByLabel("Search the catalog");
const resultItems = (page) =>
  page.getByRole("list", { name: "Results", exact: true }).getByRole("listitem");
const recentButtons = (page) =>
  page.getByRole("list", { name: "Recent searches", exact: true }).getByRole("button");

const searchResponse = (page, query) =>
  page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/search" && url.searchParams.get("q") === query;
  });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("shows matching titles and a pluralized result count as the reader types", async ({ page }) => {
  await queryInput(page).fill("dune");

  await expect(page.getByRole("status")).toHaveText('1 result for "dune"');
  await expect(resultItems(page)).toHaveText(["Dune"]);
});

test("shows an empty message when no titles match", async ({ page }) => {
  await queryInput(page).fill("zzzz");

  await expect(page.getByRole("status")).toHaveText('0 results for "zzzz"');
  await expect(page.getByText("No titles match")).toBeVisible();
  await expect(resultItems(page)).toHaveCount(0);
});

test("keeps the list aligned with the current box value after rapid typing", async ({ page }) => {
  const shortQueryResponse = searchResponse(page, "al");
  const currentQueryResponse = searchResponse(page, "alice");

  await queryInput(page).fill("al");
  await queryInput(page).fill("alice");
  await currentQueryResponse;

  await expect(page.getByRole("status")).toHaveText('1 result for "alice"');
  await expect(resultItems(page)).toHaveText(["Alice in Wonderland"]);

  await shortQueryResponse;
  await expect(page.getByRole("status")).toHaveText('1 result for "alice"');
  await expect(resultItems(page)).toHaveText(["Alice in Wonderland"]);
});

test("keeps recent searches newest first without duplicates across reloads and reruns a clicked search", async ({
  page,
}) => {
  await queryInput(page).fill("dune");
  await expect(recentButtons(page)).toHaveText(["dune"]);

  await queryInput(page).fill("alice");
  await expect(recentButtons(page)).toHaveText(["alice", "dune"]);

  await queryInput(page).fill("dune");
  await expect(recentButtons(page)).toHaveText(["dune", "alice"]);

  await page.reload();
  await expect(recentButtons(page)).toHaveText(["dune", "alice"]);

  await page.getByRole("button", { name: "alice", exact: true }).click();
  await expect(queryInput(page)).toHaveValue("alice");
  await expect(page.getByRole("status")).toHaveText('1 result for "alice"');
  await expect(resultItems(page)).toHaveText(["Alice in Wonderland"]);
});

test("clearing the box clears the status and results", async ({ page }) => {
  await queryInput(page).fill("dune");
  await expect(page.getByRole("status")).toHaveText('1 result for "dune"');
  await expect(resultItems(page)).toHaveText(["Dune"]);

  await queryInput(page).fill("");

  await expect(page.getByRole("status")).toHaveText("");
  await expect(resultItems(page)).toHaveCount(0);
});

import { expect, test } from "@playwright/test";

const addTag = async (page, tag) => {
  const input = page.getByLabel("Add a tag");
  await input.fill(tag);
  await input.press("Enter");
};

const tags = (page) => page.getByRole("list", { name: "Tags", exact: true }).getByRole("listitem");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Article tags", exact: true })).toBeVisible();
});

test("adds a tag as a chip and clears the input", async ({ page }) => {
  const input = page.getByLabel("Add a tag");

  await addTag(page, "science");

  await expect(tags(page).filter({ hasText: "science" })).toHaveCount(1);
  await expect(input).toHaveValue("");
});

test("rejects a duplicate tag regardless of case", async ({ page }) => {
  await addTag(page, "React");
  await addTag(page, "react");

  await expect(page.getByRole("alert")).toHaveText("Already added");
  await expect(tags(page)).toHaveCount(1);
});

test("removes the last chip with Backspace in an empty input", async ({ page }) => {
  const input = page.getByLabel("Add a tag");
  await addTag(page, "alpha");
  await addTag(page, "beta");
  await expect(tags(page).filter({ hasText: "beta" })).toHaveCount(1);

  await input.press("Backspace");

  await expect(tags(page)).toHaveText(["alpha\u00d7"]);
});

test("removes chips with their remove buttons", async ({ page }) => {
  await addTag(page, "alpha");
  await addTag(page, "beta");
  await addTag(page, "gamma");
  await expect(tags(page)).toHaveCount(3);
  await expect(tags(page).filter({ hasText: "beta" })).toHaveCount(1);

  await page.getByRole("button", { name: "Remove beta", exact: true }).click();
  await expect(tags(page)).toHaveText(["alpha\u00d7", "gamma\u00d7"]);

  await page.getByRole("button", { name: "Remove alpha", exact: true }).click();
  await expect(tags(page)).toHaveText(["gamma\u00d7"]);

  await page.getByRole("button", { name: "Remove gamma", exact: true }).click();
  await expect(page.getByRole("list", { name: "Tags", exact: true })).toHaveText("");
});

test("disables entry at the five-tag limit until a chip is removed", async ({ page }) => {
  const input = page.getByLabel("Add a tag");
  for (const tag of ["one", "two", "three", "four", "five"]) {
    await addTag(page, tag);
  }

  await expect(page.getByRole("alert")).toHaveText("Tag limit reached");
  await expect(input).toBeDisabled();

  await page.getByRole("button", { name: "Remove three", exact: true }).click();

  await expect(page.getByRole("alert")).toHaveText("");
  await expect(input).toBeEnabled();
});

test("saves tags and shows them after reload", async ({ page }) => {
  await addTag(page, "news");
  await addTag(page, "analysis");

  const saveRequest = page.waitForRequest((request) => (
    request.method() === "PUT" &&
    new URL(request.url()).pathname === "/api/tags" &&
    JSON.stringify(request.postDataJSON()) === JSON.stringify({ tags: ["news", "analysis"] })
  ));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await saveRequest;

  await expect(page.getByRole("status")).toHaveText("Tags saved");

  await page.reload();

  await expect(tags(page).filter({ hasText: "news" })).toHaveCount(1);
  await expect(tags(page).filter({ hasText: "analysis" })).toHaveCount(1);
});

import { expect, test } from "@playwright/test";

const addTag = async (page, tag) => {
  const input = page.getByLabel("Add a tag");
  await input.fill(tag);
  await input.press("Enter");
};

const expectTags = async (page, tags) => {
  await expect(page.getByLabel("Tags").locator("li span")).toHaveText(tags);
};

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("adds a tag, clears the input, and rejects case-insensitive duplicates", async ({ page }) => {
  const input = page.getByLabel("Add a tag");

  await addTag(page, "News");

  await expectTags(page, ["News"]);
  await expect(input).toHaveValue("");

  await addTag(page, "news");

  await expectTags(page, ["News"]);
  await expect(page.getByRole("alert")).toHaveText("Already added");
});

test("removes tags with Backspace and chip remove buttons", async ({ page }) => {
  await addTag(page, "one");
  await addTag(page, "two");
  await addTag(page, "three");

  await page.getByLabel("Add a tag").press("Backspace");

  await expectTags(page, ["one", "two"]);

  await page.getByRole("button", { name: "Remove one" }).click();

  await expectTags(page, ["two"]);
});

test("enforces the tag limit, saves tags, and reloads saved tags", async ({ page }) => {
  const input = page.getByLabel("Add a tag");

  for (const tag of ["alpha", "beta", "gamma", "delta", "epsilon"]) {
    await addTag(page, tag);
  }

  await expectTags(page, ["alpha", "beta", "gamma", "delta", "epsilon"]);
  await expect(page.getByRole("alert")).toHaveText("Tag limit reached");
  await expect(input).toBeDisabled();

  await page.getByRole("button", { name: "Remove gamma" }).click();

  await expectTags(page, ["alpha", "beta", "delta", "epsilon"]);
  await expect(page.getByRole("alert")).toBeEmpty();
  await expect(input).toBeEnabled();

  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Tags saved");

  await page.reload();

  await expectTags(page, ["alpha", "beta", "delta", "epsilon"]);
});

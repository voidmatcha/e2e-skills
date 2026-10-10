import { expect, test } from "@playwright/test";

const resetTags = async (request) => {
  await request.post("/api/reset");
};

const addTag = async (page, tag) => {
  const input = page.getByLabel("Add a tag");
  await input.fill(tag);
  await input.press("Enter");
};

test.beforeEach(async ({ page, request }) => {
  await resetTags(request);
  await page.goto("/");
});

test("adds tags, rejects duplicates, and removes the last chip with Backspace", async ({ page }) => {
  const input = page.getByLabel("Add a tag");
  const tags = page.getByRole("list", { name: "Tags", exact: true });
  const tagItems = tags.getByRole("listitem");
  const alert = page.getByRole("alert");

  await input.fill("Alpha");
  await input.press("Enter");

  await expect(tags.getByRole("listitem").filter({ hasText: "Alpha" })).toBeVisible();
  await expect(input).toHaveValue("");

  await input.fill("alpha");
  await input.press("Enter");

  await expect(alert).toHaveText("Already added");
  await expect(tagItems).toHaveCount(1);
  await expect(tags.getByRole("listitem").filter({ hasText: "Alpha" })).toBeVisible();

  await addTag(page, "Beta");
  await input.press("Backspace");

  await expect(tagItems).toHaveCount(1);
  await expect(tags.getByRole("listitem").filter({ hasText: "Alpha" })).toBeVisible();
});

test("removes a selected chip with its remove button", async ({ page }) => {
  const tags = page.getByRole("list", { name: "Tags", exact: true });
  const tagItems = tags.getByRole("listitem");

  await addTag(page, "Alpha");
  await addTag(page, "Beta");
  await tags.getByRole("button", { name: "Remove Alpha" }).click();

  await expect(tagItems).toHaveCount(1);
  await expect(tags.getByRole("listitem").filter({ hasText: "Beta" })).toBeVisible();
});

test("limits tags to five, saves them, and restores saved tags after reload", async ({ page }) => {
  const input = page.getByLabel("Add a tag");
  const tags = page.getByRole("list", { name: "Tags", exact: true });
  const tagItems = tags.getByRole("listitem");

  for (const tag of ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]) {
    await addTag(page, tag);
  }

  await expect(tagItems).toHaveCount(5);
  await expect(page.getByRole("alert")).toHaveText("Tag limit reached");
  await expect(input).toBeDisabled();

  await tags.getByRole("button", { name: "Remove Gamma" }).click();

  await expect(input).toBeEnabled();
  await expect(tagItems).toHaveCount(4);
  await expect(tags.getByRole("listitem").filter({ hasText: "Alpha" })).toBeVisible();
  await expect(tags.getByRole("listitem").filter({ hasText: "Beta" })).toBeVisible();
  await expect(tags.getByRole("listitem").filter({ hasText: "Delta" })).toBeVisible();
  await expect(tags.getByRole("listitem").filter({ hasText: "Epsilon" })).toBeVisible();

  const savedRequest = page.waitForRequest((request) => (
    request.method() === "PUT" && new URL(request.url()).pathname === "/api/tags"
  ));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const request = await savedRequest;

  expect(request.postDataJSON()).toEqual({
    tags: ["Alpha", "Beta", "Delta", "Epsilon"],
  });
  await expect(page.getByRole("status")).toHaveText("Tags saved");

  await page.reload();

  await expect(tagItems).toHaveCount(4);
  await expect(tags.getByRole("listitem").filter({ hasText: "Alpha" })).toBeVisible();
  await expect(tags.getByRole("listitem").filter({ hasText: "Beta" })).toBeVisible();
  await expect(tags.getByRole("listitem").filter({ hasText: "Delta" })).toBeVisible();
  await expect(tags.getByRole("listitem").filter({ hasText: "Epsilon" })).toBeVisible();
});

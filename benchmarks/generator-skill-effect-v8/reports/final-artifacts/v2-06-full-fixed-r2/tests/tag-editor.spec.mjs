import { expect, test } from "@playwright/test";

async function resetTags(page) {
  await page.request.post("/api/reset");
  await page.goto("/");
}

async function addTag(page, tag) {
  const tagInput = page.getByRole("textbox", { name: "Add a tag", exact: true });
  await tagInput.fill(tag);
  await tagInput.press("Enter");
}

test.beforeEach(async ({ page }) => {
  await resetTags(page);
});

test("adds a tag with Enter and rejects a duplicate ignoring case", async ({ page }) => {
  const tagInput = page.getByRole("textbox", { name: "Add a tag", exact: true });
  const tagsList = page.getByRole("list", { name: "Tags", exact: true });

  await addTag(page, "News");

  await expect(tagsList).toContainText("News");
  await expect(tagInput).toHaveValue("");

  await addTag(page, "news");

  await expect(page.getByRole("alert")).toHaveText("Already added");
  await expect(tagsList.getByRole("listitem")).toHaveCount(1);
  await expect(tagInput).toHaveValue("news");
});

test("removes tags with Backspace in the empty input and with chip buttons", async ({ page }) => {
  const tagInput = page.getByRole("textbox", { name: "Add a tag", exact: true });
  const tagsList = page.getByRole("list", { name: "Tags", exact: true });

  await addTag(page, "Alpha");
  await addTag(page, "Beta");
  await expect(page.getByRole("button", { name: "Remove Beta", exact: true })).toBeVisible();
  await expect(tagsList.getByRole("listitem")).toHaveCount(2);

  await tagInput.click();
  await tagInput.press("Backspace");

  await expect(page.getByRole("button", { name: "Remove Beta", exact: true })).not.toBeVisible();
  await expect(tagsList.getByRole("listitem")).toHaveCount(1);
  await page.getByRole("button", { name: "Remove Alpha", exact: true }).click();
  await expect(tagsList.getByRole("listitem")).toHaveCount(0);
});

test("disables the input at five tags until a chip is removed", async ({ page }) => {
  const tagInput = page.getByRole("textbox", { name: "Add a tag", exact: true });

  for (const tag of ["One", "Two", "Three", "Four", "Five"]) {
    await addTag(page, tag);
  }

  await expect(page.getByRole("alert")).toHaveText("Tag limit reached");
  await expect(tagInput).toBeDisabled();

  await page.getByRole("button", { name: "Remove Three", exact: true }).click();

  await expect(tagInput).toBeEnabled();
  await expect(page.getByRole("alert")).not.toHaveText("Tag limit reached");
});

test("saves tags and restores them after reload", async ({ page }) => {
  const tagsList = page.getByRole("list", { name: "Tags", exact: true });
  await addTag(page, "News");
  await addTag(page, "Tech");

  const saveRequest = page.waitForRequest((request) => {
    return request.method() === "PUT" && new URL(request.url()).pathname === "/api/tags";
  });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const request = await saveRequest;

  expect(request.postDataJSON()).toEqual({ tags: ["News", "Tech"] });
  await expect(page.getByRole("status")).toHaveText("Tags saved");

  await page.reload();

  await expect(tagsList).toContainText("News");
  await expect(tagsList).toContainText("Tech");
});

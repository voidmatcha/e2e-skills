import { expect, test } from "@playwright/test";

const addTag = async (page, tag) => {
  await page.getByLabel("Add a tag").fill(tag);
  await page.getByLabel("Add a tag").press("Enter");
};

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("adds a tag with Enter and clears the input", async ({ page }) => {
  await page.goto("/");

  await addTag(page, "Science");

  await expect(page.getByRole("list", { name: "Tags" }).getByText("Science")).toBeVisible();
  await expect(page.getByLabel("Add a tag")).toHaveValue("");
});

test("rejects duplicate tags regardless of case", async ({ page }) => {
  await page.goto("/");

  await addTag(page, "Science");
  await addTag(page, "science");

  await expect(page.getByRole("alert")).toHaveText("Already added");
  await expect(page.getByRole("list", { name: "Tags" }).locator("li")).toHaveCount(1);
});

test("removes the last chip with Backspace in an empty input", async ({ page }) => {
  await page.goto("/");

  await addTag(page, "Science");
  await addTag(page, "Health");
  await page.getByLabel("Add a tag").press("Backspace");

  await expect(page.getByRole("list", { name: "Tags" }).getByText("Health")).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Tags" }).getByText("Science")).toBeVisible();
});

test("removes a chip with its remove button", async ({ page }) => {
  await page.goto("/");

  await addTag(page, "Science");
  await addTag(page, "Health");
  await page.getByRole("button", { name: "Remove Science" }).click();

  await expect(page.getByRole("list", { name: "Tags" }).getByText("Science")).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Tags" }).getByText("Health")).toBeVisible();
});

test("limits the editor to five tags until one is removed", async ({ page }) => {
  await page.goto("/");

  for (const tag of ["one", "two", "three", "four", "five"]) {
    await addTag(page, tag);
  }

  await expect(page.getByRole("alert")).toHaveText("Tag limit reached");
  await expect(page.getByLabel("Add a tag")).toBeDisabled();

  await page.getByRole("button", { name: "Remove three" }).click();

  await expect(page.getByRole("alert")).toBeEmpty();
  await expect(page.getByLabel("Add a tag")).toBeEnabled();
});

test("saves tags and restores them after reload", async ({ page }) => {
  await page.goto("/");

  await addTag(page, "Science");
  await addTag(page, "Health");
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByRole("status")).toHaveText("Tags saved");

  await page.reload();

  await expect(page.getByRole("list", { name: "Tags" }).getByText("Science")).toBeVisible();
  await expect(page.getByRole("list", { name: "Tags" }).getByText("Health")).toBeVisible();
});

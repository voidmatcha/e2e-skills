import { expect, test } from "@playwright/test";

const chips = (page) => page.locator(".chip span");
const tagInput = (page) => page.getByLabel("Add a tag");

async function addTag(page, tag) {
  await tagInput(page).fill(tag);
  await tagInput(page).press("Enter");
}

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("adds tags with Enter and rejects case-insensitive duplicates", async ({ page }) => {
  await page.goto("/");

  await addTag(page, "News");

  await expect(chips(page)).toHaveText(["News"]);
  await expect(tagInput(page)).toHaveValue("");

  await addTag(page, "news");

  await expect(chips(page)).toHaveText(["News"]);
  await expect(page.getByRole("alert")).toHaveText("Already added");
});

test("removes tags with Backspace and chip remove buttons", async ({ page }) => {
  await page.goto("/");

  await addTag(page, "News");
  await addTag(page, "Tech");
  await addTag(page, "Opinion");

  await tagInput(page).press("Backspace");

  await expect(chips(page)).toHaveText(["News", "Tech"]);

  await page.getByRole("button", { name: "Remove News" }).click();

  await expect(chips(page)).toHaveText(["Tech"]);
});

test("limits tags to five until a chip is removed", async ({ page }) => {
  await page.goto("/");

  for (const tag of ["News", "Tech", "Opinion", "Sports", "Culture"]) {
    await addTag(page, tag);
  }

  await expect(chips(page)).toHaveText(["News", "Tech", "Opinion", "Sports", "Culture"]);
  await expect(page.getByRole("alert")).toHaveText("Tag limit reached");
  await expect(tagInput(page)).toBeDisabled();

  await page.getByRole("button", { name: "Remove Opinion" }).click();

  await expect(chips(page)).toHaveText(["News", "Tech", "Sports", "Culture"]);
  await expect(page.getByRole("alert")).toBeEmpty();
  await expect(tagInput(page)).toBeEnabled();
});

test("saves tags and reloads them", async ({ page }) => {
  await page.goto("/");

  await addTag(page, "News");
  await addTag(page, "Tech");
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByRole("status")).toHaveText("Tags saved");

  await page.reload();

  await expect(chips(page)).toHaveText(["News", "Tech"]);
});

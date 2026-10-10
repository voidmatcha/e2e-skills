import { expect, test } from "@playwright/test";

async function open(page) {
  const loaded = page.waitForResponse((r) => r.url().endsWith("/api/tags") && r.request().method() === "GET");
  await page.goto("/");
  await loaded;
}

async function addTag(page, tag) {
  await page.getByLabel("Add a tag").fill(tag);
  await page.getByLabel("Add a tag").press("Enter");
}

const chips = (page) => page.getByRole("list", { name: "Tags" }).getByRole("listitem");

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await open(page);
});

test("adds a tag as a chip and clears the box", async ({ page }) => {
  await addTag(page, "news");
  await expect(chips(page)).toHaveText(["news×"]);
  await expect(page.getByLabel("Add a tag")).toHaveValue("");
});

test("rejects a duplicate tag regardless of letter case", async ({ page }) => {
  await addTag(page, "News");
  await addTag(page, "nEWS");
  await expect(page.getByRole("alert")).toHaveText("Already added");
  await expect(chips(page)).toHaveCount(1);
});

test("Backspace in the empty box removes the last chip", async ({ page }) => {
  await addTag(page, "one");
  await addTag(page, "two");
  await page.getByLabel("Add a tag").press("Backspace");
  await expect(chips(page)).toHaveText(["one×"]);
});

test("Backspace with text in the box keeps the chips", async ({ page }) => {
  await addTag(page, "one");
  await page.getByLabel("Add a tag").fill("ab");
  await page.getByLabel("Add a tag").press("Backspace");
  await expect(chips(page)).toHaveCount(1);
  await expect(page.getByLabel("Add a tag")).toHaveValue("a");
});

test("a chip's remove button removes that chip", async ({ page }) => {
  await addTag(page, "one");
  await addTag(page, "two");
  await addTag(page, "three");
  await page.getByRole("button", { name: "Remove two" }).click();
  await expect(chips(page)).toHaveText(["one×", "three×"]);
});

test("limits the editor to five tags until a chip is removed", async ({ page }) => {
  for (const tag of ["a", "b", "c", "d", "e"]) await addTag(page, tag);
  await expect(chips(page)).toHaveCount(5);
  await expect(page.getByRole("alert")).toHaveText("Tag limit reached");
  await expect(page.getByLabel("Add a tag")).toBeDisabled();

  await page.getByRole("button", { name: "Remove c" }).click();
  await expect(chips(page)).toHaveCount(4);
  await expect(page.getByLabel("Add a tag")).toBeEnabled();
  await expect(page.getByRole("alert")).toHaveText("");
});

test("saves tags and shows them after a reload", async ({ page }) => {
  await addTag(page, "alpha");
  await addTag(page, "beta");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Tags saved");

  await open(page);
  await expect(chips(page)).toHaveText(["alpha×", "beta×"]);
});

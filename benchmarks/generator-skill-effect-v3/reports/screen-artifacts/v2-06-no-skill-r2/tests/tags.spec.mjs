import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  // the editor loads saved tags asynchronously; wait so typing is not overwritten
  await page.waitForLoadState("networkidle");
});

const input = (page) => page.getByLabel("Add a tag");
const chips = (page) => page.locator("#tg-chips li");

async function addTag(page, tag) {
  await input(page).fill(tag);
  await input(page).press("Enter");
}

test("Enter adds a chip and clears the box", async ({ page }) => {
  await addTag(page, "news");
  await expect(chips(page)).toHaveText(["news×"]);
  await expect(input(page)).toHaveValue("");
});

test("a duplicate tag, ignoring case, is rejected", async ({ page }) => {
  await addTag(page, "News");
  await addTag(page, "nEWS");
  await expect(page.getByRole("alert")).toHaveText("Already added");
  await expect(chips(page)).toHaveCount(1);
  await expect(chips(page).first()).toContainText("News");
});

test("Backspace in the empty box removes the last chip", async ({ page }) => {
  await addTag(page, "one");
  await addTag(page, "two");
  await input(page).press("Backspace");
  await expect(chips(page)).toHaveCount(1);
  await expect(chips(page).first()).toContainText("one");
});

test("Backspace with text in the box keeps the chips", async ({ page }) => {
  await addTag(page, "one");
  await input(page).fill("ab");
  await input(page).press("Backspace");
  await expect(chips(page)).toHaveCount(1);
  await expect(input(page)).toHaveValue("a");
});

test("a chip's remove button removes that chip", async ({ page }) => {
  await addTag(page, "one");
  await addTag(page, "two");
  await addTag(page, "three");
  await page.getByRole("button", { name: "Remove two" }).click();
  await expect(chips(page)).toHaveText(["one×", "three×"]);
});

test("the fifth tag shows the limit and disables the box until a chip is removed", async ({ page }) => {
  for (const tag of ["a", "b", "c", "d"]) await addTag(page, tag);
  await expect(input(page)).toBeEnabled();
  await expect(page.getByRole("alert")).toHaveText("");
  await addTag(page, "e");
  await expect(chips(page)).toHaveCount(5);
  await expect(page.getByRole("alert")).toHaveText("Tag limit reached");
  await expect(input(page)).toBeDisabled();

  await page.getByRole("button", { name: "Remove c" }).click();
  await expect(chips(page)).toHaveCount(4);
  await expect(input(page)).toBeEnabled();
  await expect(page.getByRole("alert")).toHaveText("");
});

test("Save stores the tags and a reload shows them", async ({ page }) => {
  await addTag(page, "alpha");
  await addTag(page, "Beta");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Tags saved");

  await page.reload();
  await expect(chips(page)).toHaveText(["alpha×", "Beta×"]);
});

test("unsaved tags are gone after a reload", async ({ page }) => {
  await addTag(page, "temp");
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(chips(page)).toHaveCount(0);
});

import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const input = (page) => page.getByLabel("Add a tag");
const chips = (page) => page.getByRole("list", { name: "Tags" }).getByRole("listitem");

async function addTags(page, ...tags) {
  for (const tag of tags) {
    await input(page).fill(tag);
    await input(page).press("Enter");
  }
}

test("Enter adds a tag as a chip and clears the box", async ({ page }) => {
  await addTags(page, "news");
  await expect(chips(page)).toHaveText(["news×"]);
  await expect(input(page)).toHaveValue("");
});

test("rejects a duplicate tag regardless of letter case", async ({ page }) => {
  await addTags(page, "News", "nEWS");
  await expect(page.getByRole("alert")).toHaveText("Already added");
  await expect(chips(page)).toHaveText(["News×"]);
});

test("Backspace in the empty box removes the last chip", async ({ page }) => {
  await addTags(page, "one", "two");
  await expect(chips(page)).toHaveCount(2);
  await input(page).press("Backspace");
  await expect(chips(page)).toHaveText(["one×"]);
});

test("Backspace with text in the box keeps the chips", async ({ page }) => {
  await addTags(page, "one");
  await input(page).fill("ab");
  await input(page).press("Backspace");
  await expect(input(page)).toHaveValue("a");
  await expect(chips(page)).toHaveCount(1);
});

test("a chip's remove button removes that chip", async ({ page }) => {
  await addTags(page, "one", "two", "three");
  await page.getByRole("button", { name: "Remove two" }).click();
  await expect(chips(page)).toHaveText(["one×", "three×"]);
});

test("the fifth tag shows the limit and disables the box until a chip is removed", async ({ page }) => {
  await addTags(page, "a", "b", "c", "d");
  await expect(input(page)).toBeEnabled();
  await expect(page.getByRole("alert")).toHaveText("");
  await addTags(page, "e");
  await expect(chips(page)).toHaveCount(5);
  await expect(page.getByRole("alert")).toHaveText("Tag limit reached");
  await expect(input(page)).toBeDisabled();

  await page.getByRole("button", { name: "Remove c" }).click();
  await expect(chips(page)).toHaveCount(4);
  await expect(input(page)).toBeEnabled();
  await expect(page.getByRole("alert")).toHaveText("");
});

test("Save stores the tags and a reload shows them", async ({ page }) => {
  await addTags(page, "alpha", "Beta");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Tags saved");

  await page.reload();
  await expect(chips(page)).toHaveText(["alpha×", "Beta×"]);
});

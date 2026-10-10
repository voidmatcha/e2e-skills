import { expect, test } from "@playwright/test";

const chips = (page) => page.locator("#tg-chips li");
const input = (page) => page.getByLabel("Add a tag");

async function addTag(page, tag) {
  await input(page).fill(tag);
  await input(page).press("Enter");
}

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(input(page)).toBeEnabled();
});

test("Enter adds a tag as a chip and clears the box", async ({ page }) => {
  await addTag(page, "news");
  await expect(chips(page)).toHaveText(["news×"]);
  await expect(input(page)).toHaveValue("");
});

test("a duplicate tag is rejected regardless of case", async ({ page }) => {
  await addTag(page, "News");
  await addTag(page, "nEWS");
  await expect(page.getByRole("alert")).toHaveText("Already added");
  await expect(chips(page)).toHaveText(["News×"]);
});

test("Backspace in the empty box removes the last chip", async ({ page }) => {
  await addTag(page, "one");
  await addTag(page, "two");
  await input(page).press("Backspace");
  await expect(chips(page)).toHaveText(["one×"]);
});

test("Backspace in a non-empty box keeps the chips", async ({ page }) => {
  await addTag(page, "one");
  await input(page).fill("tw");
  await input(page).press("Backspace");
  await expect(input(page)).toHaveValue("t");
  await expect(chips(page)).toHaveText(["one×"]);
});

test("a chip's remove button removes that chip", async ({ page }) => {
  for (const tag of ["a", "b", "c"]) await addTag(page, tag);
  await page.getByRole("button", { name: "Remove b" }).click();
  await expect(chips(page)).toHaveText(["a×", "c×"]);
});

test("the fifth tag shows the limit and disables the box until a chip is removed", async ({ page }) => {
  for (const tag of ["a", "b", "c", "d"]) await addTag(page, tag);
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

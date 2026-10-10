import { expect, test } from "@playwright/test";

const box = (page) => page.getByLabel("Add a tag");
const chips = (page) => page.getByRole("list", { name: "Tags" }).getByRole("listitem");

async function add(page, tag) {
  await box(page).fill(tag);
  await box(page).press("Enter");
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(chips(page)).toHaveCount(0);
});

test("enter adds a chip and clears the box", async ({ page }) => {
  await add(page, "node");
  await expect(chips(page)).toHaveText([/node/]);
  await expect(box(page)).toHaveValue("");
});

test("duplicates are rejected regardless of case", async ({ page }) => {
  await add(page, "node");
  await add(page, "Node");
  await expect(page.getByRole("alert")).toHaveText("Already added");
  await expect(chips(page)).toHaveCount(1);
});

test("backspace removes the last chip and the remove button removes its chip", async ({ page }) => {
  await add(page, "alpha");
  await add(page, "beta");
  await add(page, "gamma");
  await box(page).press("Backspace");
  await expect(chips(page)).toHaveText([/alpha/, /beta/]);
  await page.getByRole("button", { name: "Remove alpha" }).click();
  await expect(chips(page)).toHaveText([/beta/]);
});

test("the fifth tag reaches the limit and removing one reopens the box", async ({ page }) => {
  for (const tag of ["a", "b", "c", "d", "e"]) await add(page, tag);
  await expect(chips(page)).toHaveCount(5);
  await expect(page.getByRole("alert")).toHaveText("Tag limit reached");
  await expect(box(page)).toBeDisabled();
  await page.getByRole("button", { name: "Remove c" }).click();
  await expect(box(page)).toBeEnabled();
  await add(page, "f");
  await expect(chips(page)).toHaveCount(5);
  await expect(box(page)).toBeDisabled();
});

test("save persists the tags", async ({ page }) => {
  await add(page, "testing");
  await add(page, "playwright");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Tags saved");
  await page.reload();
  await expect(chips(page)).toHaveText([/testing/, /playwright/]);
});

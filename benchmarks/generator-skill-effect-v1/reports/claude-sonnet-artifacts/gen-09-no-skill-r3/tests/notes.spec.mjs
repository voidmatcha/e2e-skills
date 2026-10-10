import { expect, test } from "@playwright/test";

const titles = (page) => page.locator("#nt-list li .title");

async function add(page, title) {
  await page.getByLabel("Title").fill(title);
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByLabel("Title")).toHaveValue("");
}

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("0 notes")).toBeVisible();
});

test("adding a title creates a note in the list", async ({ page }) => {
  await add(page, "Buy milk");
  await expect(titles(page)).toHaveText(["Buy milk"]);
});

test("notes are listed alphabetically, ignoring case", async ({ page }) => {
  for (const t of ["banana", "Cherry", "apple", "Banana split", "avocado"]) await add(page, t);
  await expect(titles(page)).toHaveText(["apple", "avocado", "banana", "Banana split", "Cherry"]);
  await page.reload();
  await expect(titles(page)).toHaveText(["apple", "avocado", "banana", "Banana split", "Cherry"]);
});

test("Edit shows a text field and Save applies the new title to that note", async ({ page }) => {
  await add(page, "Alpha");
  await add(page, "Bravo");
  await add(page, "Charlie");
  await page.getByRole("button", { name: "Edit Bravo" }).click();
  const field = page.getByRole("textbox", { name: "New title for Bravo" });
  await expect(field).toHaveValue("Bravo");
  await field.fill("Zulu");
  await page.getByRole("button", { name: "Save Bravo" }).click();
  await expect(titles(page)).toHaveText(["Alpha", "Charlie", "Zulu"]);
  await expect(page.getByText("3 notes")).toBeVisible();
});

test("Delete removes exactly the chosen note", async ({ page }) => {
  await add(page, "Alpha");
  await add(page, "Bravo");
  await add(page, "Charlie");
  await page.getByRole("button", { name: "Delete Bravo" }).click();
  await expect(titles(page)).toHaveText(["Alpha", "Charlie"]);
  await page.reload();
  await expect(titles(page)).toHaveText(["Alpha", "Charlie"]);
});

test("Delete removes only one of several notes with the same title", async ({ page }) => {
  await add(page, "Same");
  await add(page, "Same");
  await add(page, "Other");
  await page.getByRole("button", { name: "Delete Same" }).first().click();
  await expect(titles(page)).toHaveText(["Other", "Same"]);
  await page.reload();
  await expect(titles(page)).toHaveText(["Other", "Same"]);
});

test("additions, edits and deletions persist across reload", async ({ page }) => {
  await add(page, "One");
  await add(page, "Two");
  await add(page, "Three");
  await page.getByRole("button", { name: "Edit One" }).click();
  await page.getByRole("textbox", { name: "New title for One" }).fill("Uno");
  await page.getByRole("button", { name: "Save One" }).click();
  await page.getByRole("button", { name: "Delete Two" }).click();
  await expect(titles(page)).toHaveText(["Three", "Uno"]);
  await page.reload();
  await expect(titles(page)).toHaveText(["Three", "Uno"]);
  await expect(page.getByText("2 notes")).toBeVisible();
});

test("an edited title with surrounding spaces matches after reload", async ({ page }) => {
  await add(page, "Plain");
  await page.getByRole("button", { name: "Edit Plain" }).click();
  await page.getByRole("textbox", { name: "New title for Plain" }).fill("  Padded  ");
  await page.getByRole("button", { name: "Save Plain" }).click();
  await expect(titles(page)).toHaveText(["Padded"]);
  await page.reload();
  await expect(titles(page)).toHaveText(["Padded"]);
});

test("the counter reads 1 note or N notes", async ({ page }) => {
  const count = page.locator("#nt-count");
  await expect(count).toHaveText("0 notes");
  await add(page, "A");
  await expect(count).toHaveText("1 note");
  await add(page, "B");
  await expect(count).toHaveText("2 notes");
  await page.getByRole("button", { name: "Delete A" }).click();
  await expect(count).toHaveText("1 note");
  await page.reload();
  await expect(count).toHaveText("1 note");
});

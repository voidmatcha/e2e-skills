import { expect, test } from "@playwright/test";

const noteItems = (page) => page.getByRole("list", { name: "Notes" }).getByRole("listitem");
const count = (page) => page.locator("#nt-count");

async function addNote(page, title) {
  await page.getByLabel("Title").fill(title);
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByRole("button", { name: `Edit ${title}` })).toBeVisible();
}

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.ok()).toBeTruthy();
  await page.goto("/");
  await expect(count(page)).toHaveText("0 notes");
});

test("adding a title creates a note in the list", async ({ page }) => {
  await addNote(page, "Buy milk");

  await expect(noteItems(page)).toHaveCount(1);
  await expect(noteItems(page).first()).toContainText("Buy milk");
  await expect(page.getByLabel("Title")).toHaveValue("");
});

test("lists notes alphabetically by title, ignoring case", async ({ page }) => {
  await addNote(page, "banana");
  await addNote(page, "Cherry");
  await addNote(page, "apple");
  await addNote(page, "Date");

  await expect(noteItems(page).locator(".title")).toHaveText(["apple", "banana", "Cherry", "Date"]);
});

test("Edit shows a text field and Save applies the new title to that note only", async ({ page }) => {
  await addNote(page, "Alpha");
  await addNote(page, "Bravo");

  await page.getByRole("button", { name: "Edit Alpha" }).click();
  const field = page.getByRole("textbox", { name: "New title for Alpha" });
  await expect(field).toHaveValue("Alpha");
  await field.fill("Zulu");
  await page.getByRole("button", { name: "Save Alpha" }).click();

  await expect(noteItems(page).locator(".title")).toHaveText(["Bravo", "Zulu"]);
  await expect(page.getByRole("textbox", { name: /New title for/ })).toHaveCount(0);
});

test("Delete removes exactly the chosen note", async ({ page }) => {
  await addNote(page, "One");
  await addNote(page, "Two");
  await addNote(page, "Three");

  await page.getByRole("button", { name: "Delete Two" }).click();

  await expect(noteItems(page).locator(".title")).toHaveText(["One", "Three"]);
  await expect(count(page)).toHaveText("2 notes");
});

test("additions, edits and deletions persist across a reload", async ({ page }) => {
  await addNote(page, "Keep");
  await addNote(page, "Rename me");
  await addNote(page, "Remove me");

  await page.getByRole("button", { name: "Edit Rename me" }).click();
  await page.getByRole("textbox", { name: "New title for Rename me" }).fill("Renamed");
  await page.getByRole("button", { name: "Save Rename me" }).click();
  await expect(page.getByRole("button", { name: "Edit Renamed" })).toBeVisible();
  await page.getByRole("button", { name: "Delete Remove me" }).click();
  await expect(noteItems(page)).toHaveCount(2);

  await page.reload();

  await expect(noteItems(page).locator(".title")).toHaveText(["Keep", "Renamed"]);
  await expect(count(page)).toHaveText("2 notes");
});

test("counter reads 0 notes, 1 note, then N notes", async ({ page }) => {
  await expect(count(page)).toHaveText("0 notes");

  await addNote(page, "First");
  await expect(count(page)).toHaveText("1 note");

  await addNote(page, "Second");
  await expect(count(page)).toHaveText("2 notes");

  await page.getByRole("button", { name: "Delete Second" }).click();
  await expect(count(page)).toHaveText("1 note");
});

import { expect, test } from "@playwright/test";
import { NotesPage } from "./notes-page.mjs";

let notes;

test.beforeEach(async ({ page }) => {
  notes = new NotesPage(page);
  await notes.reset();
});

test("adding a title creates a note in the list", async ({ page }) => {
  await notes.open();
  const created = page.waitForRequest(
    (r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/notes",
  );

  await notes.add("Buy milk");
  const request = await created;

  expect(request.postDataJSON()).toEqual({ title: "Buy milk" });
  await expect(notes.titles).toHaveText(["Buy milk"]);
  await expect(notes.titleInput).toHaveValue("");
});

test("lists notes alphabetically by title, ignoring letter case", async () => {
  await notes.seed(["banana", "Cherry", "apple", "Date"]);
  await notes.open();

  await expect(notes.titles).toHaveText(["apple", "banana", "Cherry", "Date"]);
});

test("a note added in the page is placed in alphabetical order", async () => {
  await notes.seed(["Apple", "cherry"]);
  await notes.open();
  await expect(notes.titles).toHaveText(["Apple", "cherry"]);

  await notes.add("banana");

  await expect(notes.titles).toHaveText(["Apple", "banana", "cherry"]);
});

test("Edit turns the title into a text field", async () => {
  await notes.seed(["Apple", "Banana"]);
  await notes.open();

  await notes.editButton("Banana").click();

  await expect(notes.editField("Banana")).toHaveValue("Banana");
  await expect(notes.saveButton("Banana")).toBeVisible();
  await expect(notes.titles).toHaveText(["Apple"]);
});

test("Save applies the new title to that note only", async ({ page }) => {
  await notes.seed(["Apple", "Banana", "Cherry"]);
  await notes.open();
  const patched = page.waitForRequest(
    (r) => r.method() === "PATCH" && /^\/api\/notes\/\d+$/.test(new URL(r.url()).pathname),
  );

  await notes.editButton("Banana").click();
  await notes.editField("Banana").fill("Zucchini");
  await notes.saveButton("Banana").click();
  const request = await patched;

  expect(request.postDataJSON()).toEqual({ title: "Zucchini" });
  await expect(notes.titles).toHaveText(["Apple", "Cherry", "Zucchini"]);
  await expect(notes.count).toHaveText("3 notes");
});

test("Delete removes exactly the chosen note", async ({ page }) => {
  await notes.seed(["Apple", "Banana", "Cherry"]);
  await notes.open();
  const deleted = page.waitForRequest(
    (r) => r.method() === "DELETE" && /^\/api\/notes\/\d+$/.test(new URL(r.url()).pathname),
  );

  await notes.deleteButton("Banana").click();
  await deleted;

  await expect(notes.titles).toHaveText(["Apple", "Cherry"]);
});

test("added notes are still listed after a reload", async () => {
  await notes.open();
  await notes.add("Beta");
  await expect(notes.titles).toHaveText(["Beta"]);
  await notes.add("alpha");
  await expect(notes.titles).toHaveText(["alpha", "Beta"]);

  await notes.reload();

  await expect(notes.titles).toHaveText(["alpha", "Beta"]);
});

test("an edited title is still shown after a reload", async () => {
  await notes.seed(["Apple", "Banana"]);
  await notes.open();
  await notes.editButton("Banana").click();
  await notes.editField("Banana").fill("Zucchini");
  await notes.saveButton("Banana").click();
  await expect(notes.titles).toHaveText(["Apple", "Zucchini"]);

  await notes.reload();

  await expect(notes.titles).toHaveText(["Apple", "Zucchini"]);
});

test("a deleted note stays gone after a reload", async () => {
  await notes.seed(["Apple", "Banana", "Cherry"]);
  await notes.open();
  await notes.deleteButton("Banana").click();
  await expect(notes.titles).toHaveText(["Apple", "Cherry"]);

  await notes.reload();

  await expect(notes.titles).toHaveText(["Apple", "Cherry"]);
});

test("the counter reads '0 notes' for an empty list", async () => {
  await notes.open();

  await expect(notes.count).toHaveText("0 notes");
});

test("the counter reads '1 note' for a single note", async () => {
  await notes.seed(["Apple"]);
  await notes.open();

  await expect(notes.count).toHaveText("1 note");
});

test("the counter follows additions and deletions", async () => {
  await notes.open();

  await notes.add("Apple");
  await expect(notes.count).toHaveText("1 note");
  await notes.add("Banana");
  await expect(notes.count).toHaveText("2 notes");
  await notes.deleteButton("Apple").click();
  await expect(notes.count).toHaveText("1 note");
});

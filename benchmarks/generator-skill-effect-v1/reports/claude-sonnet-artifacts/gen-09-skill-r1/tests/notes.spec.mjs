import { expect, test } from "@playwright/test";
import { NotesPage } from "./notes-page.mjs";

let notes;

test.beforeEach(async ({ page }) => {
  notes = new NotesPage(page);
  await notes.reset();
});

test.describe("adding", () => {
  test("adding a title creates a note in the list", async () => {
    await notes.goto();

    await notes.add("Buy milk");

    await expect(notes.titles).toHaveText(["Buy milk"]);
    await expect(notes.titleInput).toHaveValue("");
  });

  test("an added note is still listed after a reload", async ({ page }) => {
    await notes.goto();

    const created = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/notes");
    await notes.add("Buy milk");
    expect((await created).postDataJSON()).toEqual({ title: "Buy milk" });
    await expect(notes.titles).toHaveText(["Buy milk"]);

    await page.reload();

    await expect(notes.titles).toHaveText(["Buy milk"]);
  });
});

test.describe("ordering", () => {
  test("notes are listed alphabetically by title, ignoring case", async () => {
    // Lower- and upper-case first letters are mixed so a case-sensitive sort would put Mango, Zebra before apple.
    await notes.seed(["Zebra", "apple", "Mango"]);
    await notes.goto();
    await expect(notes.titles).toHaveText(["apple", "Mango", "Zebra"]);

    await notes.add("banana");

    await expect(notes.titles).toHaveText(["apple", "banana", "Mango", "Zebra"]);
  });
});

test.describe("editing", () => {
  test("Edit turns the note title into a text field holding the current title", async () => {
    await notes.seed(["Alpha", "Bravo"]);
    await notes.goto();

    await notes.editButton("Alpha").click();

    await expect(notes.editField("Alpha")).toHaveValue("Alpha");
    await expect(notes.saveButton("Alpha")).toBeVisible();
    await expect(notes.titles).toHaveText(["Bravo"]);
  });

  test("Save applies the new title to that note only", async () => {
    await notes.seed(["Alpha", "Bravo"]);
    await notes.goto();

    await notes.editButton("Alpha").click();
    await notes.editField("Alpha").fill("Zulu");
    await notes.saveButton("Alpha").click();

    // Zulu sorts after Bravo, so the order also shows the edited note was re-placed.
    await expect(notes.titles).toHaveText(["Bravo", "Zulu"]);
    await expect(notes.editField("Zulu")).toBeHidden();
  });

  test("an edited title is still shown after a reload", async ({ page }) => {
    await notes.seed(["Alpha", "Bravo"]);
    await notes.goto();

    await notes.editButton("Alpha").click();
    await notes.editField("Alpha").fill("Zulu");
    const patched = page.waitForRequest((r) => r.method() === "PATCH" && new URL(r.url()).pathname === "/api/notes/1");
    await notes.saveButton("Alpha").click();
    expect((await patched).postDataJSON()).toEqual({ title: "Zulu" });
    await expect(notes.titles).toHaveText(["Bravo", "Zulu"]);

    await page.reload();

    await expect(notes.titles).toHaveText(["Bravo", "Zulu"]);
  });
});

test.describe("deleting", () => {
  test("Delete removes exactly the chosen note", async () => {
    await notes.seed(["Alpha", "Bravo", "Charlie"]);
    await notes.goto();
    await expect(notes.titles).toHaveText(["Alpha", "Bravo", "Charlie"]);

    await notes.deleteButton("Bravo").click();

    await expect(notes.titles).toHaveText(["Alpha", "Charlie"]);
  });

  test("a deleted note stays gone after a reload", async ({ page }) => {
    await notes.seed(["Alpha", "Bravo", "Charlie"]);
    await notes.goto();
    await expect(notes.titles).toHaveText(["Alpha", "Bravo", "Charlie"]);

    const deleted = page.waitForRequest((r) => r.method() === "DELETE" && new URL(r.url()).pathname === "/api/notes/2");
    await notes.deleteButton("Bravo").click();
    await deleted;
    await expect(notes.titles).toHaveText(["Alpha", "Charlie"]);

    await page.reload();

    await expect(notes.titles).toHaveText(["Alpha", "Charlie"]);
  });
});

test.describe("counter", () => {
  test("reads '1 note' for a single note", async () => {
    await notes.seed(["Alpha"]);
    await notes.goto();

    await expect(notes.counter).toHaveText("1 note");
  });

  test("reads 'N notes' for several notes", async () => {
    await notes.seed(["Alpha", "Bravo", "Charlie"]);
    await notes.goto();

    await expect(notes.counter).toHaveText("3 notes");
  });

  test("follows additions and deletions", async () => {
    await notes.seed(["Alpha"]);
    await notes.goto();
    await expect(notes.counter).toHaveText("1 note");

    await notes.add("Bravo");
    await expect(notes.counter).toHaveText("2 notes");

    await notes.deleteButton("Alpha").click();
    await expect(notes.counter).toHaveText("1 note");

    await notes.deleteButton("Bravo").click();
    await expect(notes.counter).toHaveText("0 notes");
  });
});

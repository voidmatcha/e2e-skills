import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByText("0 notes")).toBeVisible();
});

const items = (page) => page.getByRole("list", { name: "Notes" }).getByRole("listitem");
const titles = (page) => items(page).locator(".title");

async function addNote(page, title) {
  const before = await items(page).count();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Add" }).click();
  await expect(items(page)).toHaveCount(before + 1);
}

test("adding a title creates a note in the list", async ({ page }) => {
  await addNote(page, "Buy milk");
  await expect(titles(page)).toHaveText(["Buy milk"]);
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("");
});

test("notes are listed alphabetically, ignoring case", async ({ page }) => {
  for (const t of ["banana", "Cherry", "apple", "Date"]) await addNote(page, t);
  await expect(titles(page)).toHaveText(["apple", "banana", "Cherry", "Date"]);
});

test("Edit shows a text field and Save applies the new title to that note", async ({ page }) => {
  await addNote(page, "Alpha");
  await addNote(page, "Bravo");
  await page.getByRole("button", { name: "Edit Bravo" }).click();
  const field = page.getByRole("textbox", { name: "New title for Bravo" });
  await expect(field).toHaveValue("Bravo");
  await field.fill("Zulu");
  await page.getByRole("button", { name: "Save Bravo" }).click();
  await expect(titles(page)).toHaveText(["Alpha", "Zulu"]);
  await expect(field).toHaveCount(0);
});

test("Delete removes exactly the chosen note", async ({ page }) => {
  for (const t of ["One", "Two", "Three"]) await addNote(page, t);
  await page.getByRole("button", { name: "Delete Three" }).click();
  await expect(titles(page)).toHaveText(["One", "Two"]);
});

test("additions, edits and deletions persist across reload", async ({ page }) => {
  for (const t of ["Gamma", "Alpha", "Beta"]) await addNote(page, t);
  await page.reload();
  await expect(titles(page)).toHaveText(["Alpha", "Beta", "Gamma"]);

  await page.getByRole("button", { name: "Edit Alpha" }).click();
  await page.getByRole("textbox", { name: "New title for Alpha" }).fill("Omega");
  await page.getByRole("button", { name: "Save Alpha" }).click();
  await expect(titles(page)).toHaveText(["Beta", "Gamma", "Omega"]);
  await page.reload();
  await expect(titles(page)).toHaveText(["Beta", "Gamma", "Omega"]);

  await page.getByRole("button", { name: "Delete Gamma" }).click();
  await expect(titles(page)).toHaveText(["Beta", "Omega"]);
  await page.reload();
  await expect(titles(page)).toHaveText(["Beta", "Omega"]);
  await expect(page.getByText("2 notes")).toBeVisible();
});

test("counter reads 1 note or N notes", async ({ page }) => {
  const counter = page.locator("#nt-count");
  await expect(counter).toHaveText("0 notes");
  await addNote(page, "A");
  await expect(counter).toHaveText("1 note");
  await addNote(page, "B");
  await expect(counter).toHaveText("2 notes");
  await page.getByRole("button", { name: "Delete A" }).click();
  await expect(counter).toHaveText("1 note");
  await page.reload();
  await expect(counter).toHaveText("1 note");
});

import { expect, test } from "@playwright/test";

const notes = (page) => page.getByRole("list", { name: "Notes" }).getByRole("listitem");

async function add(page, title) {
  await page.getByLabel("Title").fill(title);
  await page.getByRole("button", { name: "Add" }).click();
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("0 notes")).toBeVisible();
});

test("adds a note and counts it", async ({ page }) => {
  await add(page, "Groceries");
  await expect(notes(page)).toHaveText([/Groceries/]);
  await expect(page.getByText("1 note", { exact: true })).toBeVisible();
});

test("lists notes alphabetically ignoring case", async ({ page }) => {
  await add(page, "zebra");
  await add(page, "Apple");
  await add(page, "mango");
  await expect(notes(page)).toHaveText([/Apple/, /mango/, /zebra/]);
  await expect(page.getByText("3 notes")).toBeVisible();
});

test("edit and save rename the chosen note on the server", async ({ page }) => {
  await add(page, "Draft");
  await add(page, "Keep");
  await page.getByRole("button", { name: "Edit Draft" }).click();
  await page.getByLabel("New title for Draft").fill("Final");
  await page.getByRole("button", { name: "Save Draft" }).click();
  await expect(notes(page)).toHaveText([/Final/, /Keep/]);
  await page.reload();
  await expect(notes(page)).toHaveText([/Final/, /Keep/]);
});

test("delete removes exactly the chosen note on the server", async ({ page }) => {
  await add(page, "Alpha");
  await add(page, "Beta");
  await add(page, "Gamma");
  await page.getByRole("button", { name: "Delete Beta" }).click();
  await expect(notes(page)).toHaveText([/Alpha/, /Gamma/]);
  await expect(page.getByText("2 notes")).toBeVisible();
  await page.reload();
  await expect(notes(page)).toHaveText([/Alpha/, /Gamma/]);
});

test("additions survive a reload", async ({ page }) => {
  await add(page, "Persisted");
  await page.reload();
  await expect(notes(page)).toHaveText([/Persisted/]);
});

import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
  await page.goto("/");
  await expect(page.getByText("0 notes")).toBeVisible();
});

const titles = (page) => page.locator("#nt-list .title");
const counter = (page) => page.locator("#nt-count");

async function add(page, title) {
  const count = await page.locator("#nt-list li").count();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.locator("#nt-list li")).toHaveCount(count + 1);
}

test("adding a title creates a note in the list", async ({ page }) => {
  await add(page, "Buy milk");
  await expect(titles(page)).toHaveText(["Buy milk"]);
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("");
});

test("notes are listed alphabetically, ignoring case", async ({ page }) => {
  await add(page, "banana");
  await add(page, "Cherry");
  await add(page, "apple");
  await add(page, "Banana split");
  await expect(titles(page)).toHaveText(["apple", "banana", "Banana split", "Cherry"]);
});

test("Edit shows a text field and Save applies the new title to that note", async ({ page }) => {
  await add(page, "Alpha");
  await add(page, "Beta");
  await add(page, "Gamma");

  await page.getByRole("button", { name: "Edit Beta" }).click();
  const field = page.getByRole("textbox", { name: "New title for Beta" });
  await expect(field).toHaveValue("Beta");
  await field.fill("Zeta");
  await page.getByRole("button", { name: "Save Beta" }).click();

  await expect(titles(page)).toHaveText(["Alpha", "Gamma", "Zeta"]);
  await expect(page.getByRole("textbox", { name: /New title for/ })).toHaveCount(0);
  await expect(counter(page)).toHaveText("3 notes");
});

test("Delete removes exactly the chosen note", async ({ page }) => {
  await add(page, "Alpha");
  await add(page, "Beta");
  await add(page, "Gamma");

  await page.getByRole("button", { name: "Delete Beta" }).click();
  await expect(titles(page)).toHaveText(["Alpha", "Gamma"]);
  await expect(counter(page)).toHaveText("2 notes");
});

test("additions, edits and deletions persist across reload", async ({ page }) => {
  await add(page, "Alpha");
  await add(page, "Beta");
  await add(page, "Gamma");
  await page.reload();
  await expect(titles(page)).toHaveText(["Alpha", "Beta", "Gamma"]);

  await page.getByRole("button", { name: "Edit Beta" }).click();
  await page.getByRole("textbox", { name: "New title for Beta" }).fill("delta");
  await page.getByRole("button", { name: "Save Beta" }).click();
  await expect(titles(page)).toHaveText(["Alpha", "delta", "Gamma"]);
  await page.reload();
  await expect(titles(page)).toHaveText(["Alpha", "delta", "Gamma"]);

  await page.getByRole("button", { name: "Delete Alpha" }).click();
  await expect(titles(page)).toHaveText(["delta", "Gamma"]);
  await page.reload();
  await expect(titles(page)).toHaveText(["delta", "Gamma"]);
  await expect(counter(page)).toHaveText("2 notes");
});

test("counter reads '1 note' or 'N notes'", async ({ page }) => {
  await expect(counter(page)).toHaveText("0 notes");
  await add(page, "One");
  await expect(counter(page)).toHaveText("1 note");
  await add(page, "Two");
  await expect(counter(page)).toHaveText("2 notes");
  await page.getByRole("button", { name: "Delete One" }).click();
  await expect(counter(page)).toHaveText("1 note");
  await page.reload();
  await expect(counter(page)).toHaveText("1 note");
});

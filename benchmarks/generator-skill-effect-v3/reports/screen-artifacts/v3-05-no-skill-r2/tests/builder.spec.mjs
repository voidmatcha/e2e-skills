import { expect, test } from "@playwright/test";

const Q1 = "How did you hear about us?";
const Q2 = "Which features do you use?";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
  await page.goto("/");
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");
});

const optionsOf = (page, q) => page.getByRole("list", { name: `Options for ${q}` }).locator(".option-text");
const headings = (page) => page.locator("#sb-questions h2");

test("seeded survey shows both questions with their options", async ({ page }) => {
  await expect(headings(page)).toHaveText([`Q1: ${Q1}`, `Q2: ${Q2}`]);
  await expect(optionsOf(page, Q1)).toHaveText(["Friend", "Search", "Advert"]);
  await expect(optionsOf(page, Q2)).toHaveText(["Export", "Sharing"]);
});

test("add option affects only that question and updates the counter", async ({ page }) => {
  await page.getByRole("textbox", { name: `New option for ${Q2}` }).fill("Reports");
  await page.getByRole("button", { name: `Add option to ${Q2}` }).click();
  await expect(optionsOf(page, Q2)).toHaveText(["Export", "Sharing", "Reports"]);
  await expect(optionsOf(page, Q1)).toHaveText(["Friend", "Search", "Advert"]);
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 6 options");
});

test("remove option removes exactly that option", async ({ page }) => {
  await page.getByRole("button", { name: `Remove option Search from ${Q1}` }).click();
  await expect(optionsOf(page, Q1)).toHaveText(["Friend", "Advert"]);
  await expect(optionsOf(page, Q2)).toHaveText(["Export", "Sharing"]);
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 4 options");
});

test("move question down and up reorders questions", async ({ page }) => {
  await page.getByRole("button", { name: `Move question down: ${Q1}` }).click();
  await expect(headings(page)).toHaveText([`Q1: ${Q2}`, `Q2: ${Q1}`]);
  await page.getByRole("button", { name: `Move question up: ${Q1}` }).click();
  await expect(headings(page)).toHaveText([`Q1: ${Q1}`, `Q2: ${Q2}`]);
});

test("preview renders questions in order with radios and checkboxes", async ({ page }) => {
  const preview = page.getByRole("region", { name: "Preview" });
  await expect(preview).toBeHidden();
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("button", { name: "Hide preview" })).toBeVisible();
  await expect(preview).toBeVisible();
  await expect(preview.locator("legend")).toHaveText([`1. ${Q1}`, `2. ${Q2}`]);
  await expect(preview.getByRole("group", { name: `1. ${Q1}` }).getByRole("radio")).toHaveCount(3);
  await expect(preview.getByRole("radio", { name: "Friend" })).toBeVisible();
  await expect(preview.getByRole("group", { name: `2. ${Q2}` }).getByRole("checkbox")).toHaveCount(2);
  await expect(preview.getByRole("checkbox", { name: "Export" })).toBeVisible();

  await page.getByRole("button", { name: "Hide preview" }).click();
  await expect(preview).toBeHidden();
  await expect(page.getByRole("button", { name: "Preview" })).toBeVisible();
});

test("preview reflects reordering and option edits", async ({ page }) => {
  await page.getByRole("button", { name: `Move question up: ${Q2}` }).click();
  await page.getByRole("button", { name: `Remove option Export from ${Q2}` }).click();
  await page.getByRole("button", { name: "Preview" }).click();
  const preview = page.getByRole("region", { name: "Preview" });
  await expect(preview.locator("legend")).toHaveText([`1. ${Q2}`, `2. ${Q1}`]);
  await expect(preview.getByRole("group", { name: `1. ${Q2}` }).getByRole("checkbox")).toHaveCount(1);
});

test("options and order survive a reload", async ({ page }) => {
  await page.getByRole("textbox", { name: `New option for ${Q1}` }).fill("Podcast");
  await page.getByRole("button", { name: `Add option to ${Q1}` }).click();
  await page.getByRole("button", { name: `Remove option Sharing from ${Q2}` }).click();
  await page.getByRole("button", { name: `Move question down: ${Q1}` }).click();
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");

  await page.reload();
  await expect(headings(page)).toHaveText([`Q1: ${Q2}`, `Q2: ${Q1}`]);
  await expect(optionsOf(page, Q1)).toHaveText(["Friend", "Search", "Advert", "Podcast"]);
  await expect(optionsOf(page, Q2)).toHaveText(["Export"]);
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");
});

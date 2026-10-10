import { expect, test } from "@playwright/test";

const Q1 = "How did you hear about us?";
const Q2 = "Which features do you use?";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");
});

const optionsOf = (page, question) => page.getByRole("list", { name: `Options for ${question}` });

test("seeds two questions with their options", async ({ page }) => {
  await expect(page.getByRole("heading", { level: 2 })).toHaveText([`Q1: ${Q1}`, `Q2: ${Q2}`]);
  await expect(optionsOf(page, Q1).locator(".option-text")).toHaveText(["Friend", "Search", "Advert"]);
  await expect(optionsOf(page, Q2).locator(".option-text")).toHaveText(["Export", "Sharing"]);
});

test("adds an option to that question only and updates the counter", async ({ page }) => {
  await page.getByRole("textbox", { name: `New option for ${Q2}` }).fill("Reports");
  await page.getByRole("button", { name: `Add option to ${Q2}` }).click();

  await expect(optionsOf(page, Q2).locator(".option-text")).toHaveText(["Export", "Sharing", "Reports"]);
  await expect(optionsOf(page, Q1).locator(".option-text")).toHaveText(["Friend", "Search", "Advert"]);
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 6 options");
});

test("removes exactly the chosen option and updates the counter", async ({ page }) => {
  await page.getByRole("button", { name: `Remove option Search from ${Q1}` }).click();

  await expect(optionsOf(page, Q1).locator(".option-text")).toHaveText(["Friend", "Advert"]);
  await expect(optionsOf(page, Q2).locator(".option-text")).toHaveText(["Export", "Sharing"]);
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 4 options");
});

test("option changes survive a reload", async ({ page }) => {
  await page.getByRole("textbox", { name: `New option for ${Q1}` }).fill("Podcast");
  await page.getByRole("button", { name: `Add option to ${Q1}` }).click();
  await page.getByRole("button", { name: `Remove option Export from ${Q2}` }).click();
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");

  await page.reload();
  await expect(optionsOf(page, Q1).locator(".option-text")).toHaveText(["Friend", "Search", "Advert", "Podcast"]);
  await expect(optionsOf(page, Q2).locator(".option-text")).toHaveText(["Sharing"]);
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");
});

test("moves questions down and up, and the order survives a reload", async ({ page }) => {
  const headings = page.getByRole("heading", { level: 2 });

  await page.getByRole("button", { name: `Move question down: ${Q1}` }).click();
  await expect(headings).toHaveText([`Q1: ${Q2}`, `Q2: ${Q1}`]);

  await page.reload();
  await expect(headings).toHaveText([`Q1: ${Q2}`, `Q2: ${Q1}`]);

  await page.getByRole("button", { name: `Move question up: ${Q1}` }).click();
  await expect(headings).toHaveText([`Q1: ${Q1}`, `Q2: ${Q2}`]);
});

test("edge questions cannot move past the ends", async ({ page }) => {
  await expect(page.getByRole("button", { name: `Move question up: ${Q1}` })).toBeDisabled();
  await expect(page.getByRole("button", { name: `Move question down: ${Q2}` })).toBeDisabled();
});

test("preview renders questions with radios and checkboxes", async ({ page }) => {
  const preview = page.getByRole("region", { name: "Preview" });
  await expect(preview).toBeHidden();

  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("button", { name: "Hide preview" })).toBeVisible();
  await expect(preview).toBeVisible();

  const single = preview.getByRole("group", { name: `1. ${Q1}` });
  await expect(single.getByRole("radio")).toHaveCount(3);
  await expect(single.getByRole("radio", { name: "Friend" })).toBeVisible();
  await expect(single.getByRole("radio", { name: "Search" })).toBeVisible();
  await expect(single.getByRole("radio", { name: "Advert" })).toBeVisible();

  const multiple = preview.getByRole("group", { name: `2. ${Q2}` });
  await expect(multiple.getByRole("checkbox")).toHaveCount(2);
  await expect(multiple.getByRole("checkbox", { name: "Export" })).toBeVisible();
  await expect(multiple.getByRole("checkbox", { name: "Sharing" })).toBeVisible();

  await page.getByRole("button", { name: "Hide preview" }).click();
  await expect(preview).toBeHidden();
  await expect(page.getByRole("button", { name: "Preview" })).toBeVisible();
});

test("preview reflects current order and options", async ({ page }) => {
  await page.getByRole("button", { name: `Move question up: ${Q2}` }).click();
  await page.getByRole("button", { name: `Remove option Friend from ${Q1}` }).click();
  await page.getByRole("button", { name: "Preview" }).click();

  const preview = page.getByRole("region", { name: "Preview" });
  await expect(preview.locator("legend")).toHaveText([`1. ${Q2}`, `2. ${Q1}`]);
  const first = preview.getByRole("group", { name: `1. ${Q2}` });
  await expect(first.getByRole("checkbox")).toHaveCount(2);
  const second = preview.getByRole("group", { name: `2. ${Q1}` });
  await expect(second.getByRole("radio")).toHaveCount(2);
  await expect(second.getByRole("radio", { name: "Friend" })).toHaveCount(0);
});

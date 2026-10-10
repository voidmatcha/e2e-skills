import { expect, test } from "@playwright/test";

const Q1 = "How did you hear about us?";
const Q2 = "Which features do you use?";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");
});

const options = (page, question) => page.getByRole("list", { name: `Options for ${question}` }).locator(".option-text");
const headings = (page) => page.locator("#sb-questions h2");

async function addOption(page, question, text) {
  await page.getByRole("textbox", { name: `New option for ${question}` }).fill(text);
  await page.getByRole("button", { name: `Add option to ${question}` }).click();
}

test("shows the seeded questions and options", async ({ page }) => {
  await expect(headings(page)).toHaveText([`Q1: ${Q1}`, `Q2: ${Q2}`]);
  await expect(options(page, Q1)).toHaveText(["Friend", "Search", "Advert"]);
  await expect(options(page, Q2)).toHaveText(["Export", "Sharing"]);
});

test("adds an option to that question only and updates the counter", async ({ page }) => {
  await addOption(page, Q2, "Reports");
  await expect(options(page, Q2)).toHaveText(["Export", "Sharing", "Reports"]);
  await expect(options(page, Q1)).toHaveText(["Friend", "Search", "Advert"]);
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 6 options");
});

test("removes exactly the chosen option and updates the counter", async ({ page }) => {
  await page.getByRole("button", { name: `Remove option Search from ${Q1}` }).click();
  await expect(options(page, Q1)).toHaveText(["Friend", "Advert"]);
  await expect(options(page, Q2)).toHaveText(["Export", "Sharing"]);
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 4 options");
});

test("added and removed options survive a reload", async ({ page }) => {
  await addOption(page, Q1, "Podcast");
  await expect(options(page, Q1)).toHaveText(["Friend", "Search", "Advert", "Podcast"]);
  await page.getByRole("button", { name: `Remove option Export from ${Q2}` }).click();
  await expect(options(page, Q2)).toHaveText(["Sharing"]);
  await page.reload();
  await expect(page.locator("#sb-counter")).toHaveText("2 questions · 5 options");
  await expect(options(page, Q1)).toHaveText(["Friend", "Search", "Advert", "Podcast"]);
  await expect(options(page, Q2)).toHaveText(["Sharing"]);
});

test("moves questions down and up, and the order survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: `Move question down: ${Q1}` }).click();
  await expect(headings(page)).toHaveText([`Q1: ${Q2}`, `Q2: ${Q1}`]);
  await page.reload();
  await expect(headings(page)).toHaveText([`Q1: ${Q2}`, `Q2: ${Q1}`]);
  await page.getByRole("button", { name: `Move question up: ${Q1}` }).click();
  await expect(headings(page)).toHaveText([`Q1: ${Q1}`, `Q2: ${Q2}`]);
});

test("disables moving the first question up and the last down", async ({ page }) => {
  await expect(page.getByRole("button", { name: `Move question up: ${Q1}` })).toBeDisabled();
  await expect(page.getByRole("button", { name: `Move question down: ${Q2}` })).toBeDisabled();
});

test("preview renders questions with radios and checkboxes", async ({ page }) => {
  const preview = page.getByRole("region", { name: "Preview" });
  await expect(preview).toBeHidden();
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("button", { name: "Hide preview" })).toBeVisible();
  await expect(preview).toBeVisible();
  await expect(preview.locator("legend")).toHaveText([`1. ${Q1}`, `2. ${Q2}`]);
  const single = preview.getByRole("group", { name: `1. ${Q1}` });
  await expect(single.getByRole("radio")).toHaveCount(3);
  for (const name of ["Friend", "Search", "Advert"]) await expect(single.getByRole("radio", { name })).toBeVisible();
  const multi = preview.getByRole("group", { name: `2. ${Q2}` });
  await expect(multi.getByRole("checkbox")).toHaveCount(2);
  for (const name of ["Export", "Sharing"]) await expect(multi.getByRole("checkbox", { name })).toBeVisible();

  await page.getByRole("button", { name: "Hide preview" }).click();
  await expect(preview).toBeHidden();
  await expect(page.getByRole("button", { name: "Preview" })).toBeVisible();
});

test("preview reflects current order and options", async ({ page }) => {
  await page.getByRole("button", { name: `Move question up: ${Q2}` }).click();
  await expect(headings(page)).toHaveText([`Q1: ${Q2}`, `Q2: ${Q1}`]);
  await addOption(page, Q2, "Reports");
  await expect(options(page, Q2)).toHaveText(["Export", "Sharing", "Reports"]);
  await page.getByRole("button", { name: `Remove option Friend from ${Q1}` }).click();
  await expect(options(page, Q1)).toHaveText(["Search", "Advert"]);
  await page.getByRole("button", { name: "Preview" }).click();
  const preview = page.getByRole("region", { name: "Preview" });
  await expect(preview.locator("legend")).toHaveText([`1. ${Q2}`, `2. ${Q1}`]);
  await expect(preview.getByRole("group", { name: `1. ${Q2}` }).getByRole("checkbox")).toHaveCount(3);
  await expect(preview.getByRole("group", { name: `1. ${Q2}` }).getByRole("checkbox", { name: "Reports" })).toBeVisible();
  const single = preview.getByRole("group", { name: `2. ${Q1}` });
  await expect(single.getByRole("radio")).toHaveCount(2);
  await expect(single.getByRole("radio", { name: "Friend" })).toHaveCount(0);
});

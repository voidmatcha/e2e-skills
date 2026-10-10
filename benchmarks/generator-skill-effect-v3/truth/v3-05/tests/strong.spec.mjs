import { expect, test } from "@playwright/test";

const Q1 = "How did you hear about us?";
const Q2 = "Which features do you use?";
const options = (page, q) => page.getByRole("list", { name: `Options for ${q}` }).getByRole("listitem");
const counter = (page) => page.getByText(/^\d+ questions? · \d+ options?$/);
const cards = (page) => page.getByRole("article");

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(counter(page)).toHaveText("2 questions · 5 options");
});

test("add and remove options on the right question, counter follows, persists", async ({ page }) => {
  await page.getByRole("textbox", { name: `New option for ${Q2}` }).fill("Reports");
  await page.getByRole("button", { name: `Add option to ${Q2}` }).click();
  await expect(options(page, Q2)).toHaveText([/Export/, /Sharing/, /Reports/]);
  await expect(options(page, Q1)).toHaveCount(3);
  await expect(counter(page)).toHaveText("2 questions · 6 options");
  await page.getByRole("button", { name: `Remove option Search from ${Q1}` }).click();
  await expect(options(page, Q1)).toHaveText([/Friend/, /Advert/]);
  await expect(counter(page)).toHaveText("2 questions · 5 options");
  await page.reload();
  await expect(options(page, Q1)).toHaveText([/Friend/, /Advert/]);
  await expect(options(page, Q2)).toHaveText([/Export/, /Sharing/, /Reports/]);
});

test("moving a question reorders the cards and the preview", async ({ page }) => {
  await page.getByRole("button", { name: `Move question up: ${Q2}` }).click();
  await expect(cards(page).first()).toContainText(Q2);
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("button", { name: "Hide preview" })).toBeVisible();
  const preview = page.getByRole("region", { name: "Preview" });
  await expect(preview.getByRole("group")).toHaveText([new RegExp(`1\\. ${Q2.replace("?", "\\?")}`), new RegExp(`2\\. ${Q1.replace("?", "\\?")}`)]);
  await expect(preview.getByRole("group").first().getByRole("checkbox")).toHaveCount(2);
  await expect(preview.getByRole("group").nth(1).getByRole("radio")).toHaveCount(3);
  await page.reload();
  await expect(cards(page).first()).toContainText(Q2);
});

import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
});

test("autosaves the draft and restores it after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Title").fill("A field note from the editor");
  await page.getByLabel("Body").fill("The body keeps the exact last text the author typed.");

  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.reload();

  await expect(page.getByLabel("Title")).toHaveValue("A field note from the editor");
  await expect(page.getByLabel("Body")).toHaveValue("The body keeps the exact last text the author typed.");
});

test("publishes the post, empties the editor, and clears the stored draft", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Title").fill("Published from the editor");
  await page.getByLabel("Body").fill("This draft should become a post.");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Publish" }).click();

  await expect(page.getByLabel("Published posts")).toContainText("Published from the editor");
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");

  await page.reload();

  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
  await expect(page.getByLabel("Published posts")).toContainText("Published from the editor");
});

test("discards the draft, empties the editor, and clears the stored draft", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Title").fill("Draft to discard");
  await page.getByLabel("Body").fill("This text should not survive discard.");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Discard draft" }).click();

  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");

  await page.reload();

  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
});

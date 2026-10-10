import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("autosaves the draft and restores it after reload", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Title").fill("A saved draft");
  await page.getByLabel("Body").fill("This body should survive a reload.");

  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.reload();

  await expect(page.getByLabel("Title")).toHaveValue("A saved draft");
  await expect(page.getByLabel("Body")).toHaveValue("This body should survive a reload.");
});

test("publishing adds the post, empties the editor, and clears the stored draft", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Title").fill("Published title");
  await page.getByLabel("Body").fill("Published body text.");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Publish" }).click();

  await expect(page.getByLabel("Published posts")).toContainText("Published title");
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");

  await page.reload();

  await expect(page.getByLabel("Published posts")).toContainText("Published title");
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
});

test("discarding empties the editor and clears the stored draft", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Title").fill("Unwanted draft");
  await page.getByLabel("Body").fill("This should be discarded.");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Discard draft" }).click();

  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");

  await page.reload();

  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
});

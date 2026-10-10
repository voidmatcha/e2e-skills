import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

const title = (page) => page.getByLabel("Title");
const body = (page) => page.getByLabel("Body");
const status = (page) => page.getByRole("status");
const posts = (page) => page.getByRole("list", { name: "Published posts" });

test("autosaves the draft and restores title and body after reload", async ({ page }) => {
  await title(page).fill("My title");
  await body(page).fill("First line\nSecond line");
  await expect(status(page)).toHaveText("Draft saved");

  await page.reload();
  await expect(title(page)).toHaveValue("My title");
  await expect(body(page)).toHaveValue("First line\nSecond line");
});

test("reload restores the draft exactly as last typed after further edits", async ({ page }) => {
  await title(page).fill("Old title");
  await body(page).fill("Old body");
  await expect(status(page)).toHaveText("Draft saved");

  await title(page).fill("  New title ");
  await body(page).clear();
  await body(page).pressSequentially("Newer body  ", { delay: 50 });
  await expect(status(page)).toHaveText("Draft saved");

  await page.reload();
  await expect(title(page)).toHaveValue("  New title ");
  await expect(body(page)).toHaveValue("Newer body  ");
});

test("editing only the body is saved without losing the title", async ({ page }) => {
  await title(page).fill("Keep me");
  await expect(status(page)).toHaveText("Draft saved");
  await body(page).fill("Added later");
  await expect(status(page)).toHaveText("Draft saved");

  await page.reload();
  await expect(title(page)).toHaveValue("Keep me");
  await expect(body(page)).toHaveValue("Added later");
});

test("publish adds the post, empties the editor and clears the stored draft", async ({ page }) => {
  await title(page).fill("Hello world");
  await body(page).fill("Post body");
  await expect(status(page)).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(posts(page).getByRole("listitem")).toHaveText(["Hello world"]);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");

  await page.reload();
  await expect(posts(page).getByRole("listitem")).toHaveText(["Hello world"]);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
});

test("publish right after typing does not resurrect the draft", async ({ page }) => {
  await title(page).fill("Quick post");
  await body(page).fill("Quick body");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(posts(page).getByRole("listitem")).toHaveText(["Quick post"]);

  // Wait longer than the autosave debounce, then reload.
  await page.waitForTimeout(800);
  await page.reload();
  await expect(posts(page).getByRole("listitem")).toHaveText(["Quick post"]);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
});

test("discard draft empties the editor and clears the stored draft", async ({ page }) => {
  await title(page).fill("Throwaway");
  await body(page).fill("Throwaway body");
  await expect(status(page)).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Discard draft" }).click();
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");

  await page.reload();
  await expect(posts(page).getByRole("listitem")).toHaveCount(0);
  await page.waitForTimeout(500);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
});

test("discard right after typing does not resurrect the draft", async ({ page }) => {
  await title(page).fill("Gone");
  await body(page).fill("Gone body");
  await page.getByRole("button", { name: "Discard draft" }).click();

  await page.waitForTimeout(800);
  await page.reload();
  await page.waitForTimeout(500);
  await expect(title(page)).toHaveValue("");
  await expect(body(page)).toHaveValue("");
});

test("publish without a title is rejected and keeps the draft", async ({ page }) => {
  await body(page).fill("Body only");
  await expect(status(page)).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(status(page)).toHaveText("A title is required to publish");
  await expect(posts(page).getByRole("listitem")).toHaveCount(0);
  await expect(body(page)).toHaveValue("Body only");
});

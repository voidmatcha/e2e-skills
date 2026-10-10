import { expect, test } from "@playwright/test";

const TITLE = "My first post";
const BODY = "Line one\nLine two  with  spaces\n\nLast line ";

// The page fills the fields from /api/state after load; wait for that so it
// cannot overwrite what a test types.
async function openEditor(page) {
  const state = page.waitForResponse((r) => r.url().endsWith("/api/state"));
  await page.goto("/");
  await state;
  await expect(page.getByRole("heading", { name: "Editor" })).toBeVisible();
}

test.beforeEach(async ({ request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
});

test("autosaves the draft and restores title and body after a reload", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Title").fill(TITLE);
  await page.getByLabel("Body").fill(BODY);
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await openEditor(page);
  await expect(page.getByLabel("Title")).toHaveValue(TITLE);
  await expect(page.getByLabel("Body")).toHaveValue(BODY);
});

test("restores the last typed text when the draft is edited repeatedly", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Title").pressSequentially("Draft title", { delay: 50 });
  await page.getByLabel("Body").pressSequentially("first body", { delay: 50 });
  await expect(page.getByRole("status")).toHaveText("Draft saved");
  await page.getByLabel("Body").pressSequentially(" and more", { delay: 50 });
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await openEditor(page);
  await expect(page.getByLabel("Title")).toHaveValue("Draft title");
  await expect(page.getByLabel("Body")).toHaveValue("first body and more");
});

test("publish adds the post, empties the editor and clears the stored draft", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Title").fill(TITLE);
  await page.getByLabel("Body").fill(BODY);
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByRole("status")).toHaveText("Published");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveText([TITLE]);
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");

  await openEditor(page);
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveText([TITLE]);
});

test("publish right after typing does not let a pending autosave resurrect the draft", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Title").fill(TITLE);
  await page.getByLabel("Body").fill("quick body");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByRole("status")).toHaveText("Published");
  // Outlast the 300 ms debounce window.
  await page.waitForTimeout(600);

  await openEditor(page);
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
});

test("publishing without a title is rejected and keeps the draft", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Body").fill("body only");
  await expect(page.getByRole("status")).toHaveText("Draft saved");
  await page.getByRole("button", { name: "Publish" }).click();

  await expect(page.getByRole("status")).toHaveText("A title is required to publish");
  await expect(page.getByLabel("Body")).toHaveValue("body only");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveCount(0);
});

test("discard draft empties the editor and clears the stored draft", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Title").fill(TITLE);
  await page.getByLabel("Body").fill(BODY);
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Discard draft" }).click();
  await expect(page.getByRole("status")).toHaveText("Draft discarded");
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");

  await openEditor(page);
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveCount(0);
});

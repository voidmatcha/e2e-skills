import { expect, test } from "@playwright/test";

// The page fills the fields from /api/state after load; wait for that so it
// cannot overwrite what the test types.
async function openEditor(page) {
  const loaded = page.waitForResponse((r) => r.url().endsWith("/api/state"));
  await page.goto("/");
  await loaded;
  // Response received; let the page's .then() handlers run.
  await page.waitForFunction(() => document.readyState === "complete");
}

async function reloadEditor(page) {
  const loaded = page.waitForResponse((r) => r.url().endsWith("/api/state"));
  await page.reload();
  await loaded;
}

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("autosaves the title and body and restores them after a reload", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Title").fill("My title");
  await page.getByLabel("Body").fill("My body text");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await reloadEditor(page);
  await expect(page.getByLabel("Title")).toHaveValue("My title");
  await expect(page.getByLabel("Body")).toHaveValue("My body text");
});

test("a reload restores the draft exactly as last typed after slow typing", async ({ page }) => {
  await openEditor(page);
  const title = page.getByLabel("Title");
  const body = page.getByLabel("Body");
  // Pauses longer than the 300 ms debounce force intermediate saves.
  await title.pressSequentially("Slow", { delay: 400 });
  await body.pressSequentially("typing here", { delay: 400 });
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await reloadEditor(page);
  await expect(title).toHaveValue("Slow");
  await expect(body).toHaveValue("typing here");
});

test("a later edit replaces the saved draft", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Title").fill("First");
  await expect(page.getByRole("status")).toHaveText("Draft saved");
  await page.getByLabel("Title").fill("Second");
  await page.getByLabel("Body").fill("Edited body");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await reloadEditor(page);
  await expect(page.getByLabel("Title")).toHaveValue("Second");
  await expect(page.getByLabel("Body")).toHaveValue("Edited body");
});

test("publish adds the post, empties the editor and clears the stored draft", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Title").fill("Hello world");
  await page.getByLabel("Body").fill("Post body");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveText(["Hello world"]);
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");

  await reloadEditor(page);
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveText(["Hello world"]);
});

test("publish without a title is rejected and keeps the draft", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Body").fill("Only a body");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByRole("status")).toHaveText("A title is required to publish");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveCount(0);
  await expect(page.getByLabel("Body")).toHaveValue("Only a body");
});

test("discard draft empties the editor and clears the stored draft", async ({ page }) => {
  await openEditor(page);
  await page.getByLabel("Title").fill("Throwaway");
  await page.getByLabel("Body").fill("Not needed");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Discard draft" }).click();
  await expect(page.getByRole("status")).toHaveText("Draft discarded");
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");

  await reloadEditor(page);
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveCount(0);
});

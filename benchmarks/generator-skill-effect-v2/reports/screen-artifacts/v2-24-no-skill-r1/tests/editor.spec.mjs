import { expect, test } from "@playwright/test";

const isState = (r) => new URL(r.url()).pathname === "/api/state";

// The page fills the editor from /api/state after load, so wait for it
// before typing or asserting on a reloaded editor.
async function open(page) {
  const loaded = page.waitForResponse(isState);
  await page.goto("/");
  await loaded;
}

async function reload(page) {
  const loaded = page.waitForResponse(isState);
  await page.reload();
  await loaded;
}

test.beforeEach(async ({ request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
});

test("autosaves the draft and restores title and body after a reload", async ({ page }) => {
  await open(page);
  await page.getByLabel("Title").fill("My title");
  await page.getByLabel("Body").fill("First line\nSecond line  with  spaces");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await reload(page);
  await expect(page.getByLabel("Title")).toHaveValue("My title");
  await expect(page.getByLabel("Body")).toHaveValue("First line\nSecond line  with  spaces");
});

test("the saved draft is exactly the last typed text", async ({ page, request }) => {
  await open(page);
  await page.getByLabel("Title").pressSequentially("Hello wor");
  await page.getByLabel("Body").pressSequentially("abc");
  await page.getByLabel("Title").press("End");
  await page.getByLabel("Title").pressSequentially("ld");
  await page.getByLabel("Body").press("End");
  await page.getByLabel("Body").pressSequentially("def");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  const state = await (await request.get("/api/state")).json();
  expect(state.draft).toEqual({ title: "Hello world", body: "abcdef" });

  await reload(page);
  await expect(page.getByLabel("Title")).toHaveValue("Hello world");
  await expect(page.getByLabel("Body")).toHaveValue("abcdef");
});

test("publishing adds the post, empties the editor and clears the draft", async ({ page, request }) => {
  await open(page);
  await page.getByLabel("Title").fill("Published title");
  await page.getByLabel("Body").fill("Published body");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveText(["Published title"]);
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");

  const state = await (await request.get("/api/state")).json();
  expect(state.draft).toEqual({ title: "", body: "" });

  await reload(page);
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveText(["Published title"]);
});

test("publishing without a title is rejected and keeps the draft", async ({ page }) => {
  await open(page);
  await page.getByLabel("Body").fill("Body only");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByRole("status")).toHaveText("A title is required to publish");
  await expect(page.getByLabel("Body")).toHaveValue("Body only");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveCount(0);
});

test("discarding empties the editor and clears the stored draft", async ({ page, request }) => {
  await open(page);
  await page.getByLabel("Title").fill("Throwaway");
  await page.getByLabel("Body").fill("Throwaway body");
  await expect(page.getByRole("status")).toHaveText("Draft saved");

  await page.getByRole("button", { name: "Discard draft" }).click();
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");

  const state = await (await request.get("/api/state")).json();
  expect(state.draft).toEqual({ title: "", body: "" });

  await reload(page);
  await expect(page.getByLabel("Title")).toHaveValue("");
  await expect(page.getByLabel("Body")).toHaveValue("");
  await expect(page.getByRole("list", { name: "Published posts" }).getByRole("listitem")).toHaveCount(0);
});

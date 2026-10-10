import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("0 comments")).toBeVisible();
});

async function post(page, text) {
  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post" }).click();
  await expect(page.getByText(text)).toBeVisible();
}

async function reply(page, id, text) {
  await page.getByRole("button", { name: `Reply to comment #${id}` }).click();
  await post(page, text);
}

test("posts a comment and updates the counter", async ({ page }) => {
  await post(page, "Hello world");
  await expect(page.getByRole("list", { name: "Comments" }).getByText("#1 Hello world")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
  await expect(page.getByLabel("Your comment")).toHaveValue("");
});

test("a reply nests under the comment it answers, not another one", async ({ page }) => {
  await post(page, "First");
  await post(page, "Second");
  await reply(page, 2, "Answer to second");

  const second = page.getByRole("list", { name: "Replies to comment #2" });
  await expect(second.getByText("#3 Answer to second")).toBeVisible();
  await expect(page.getByRole("list", { name: "Replies to comment #1" })).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("3 comments");
});

test("counter counts replies too", async ({ page }) => {
  await post(page, "Root");
  await reply(page, 1, "Child one");
  await reply(page, 1, "Child two");
  await expect(page.locator("#cm-count")).toHaveText("3 comments");
  await expect(page.getByRole("list", { name: "Replies to comment #1" }).getByRole("listitem")).toHaveCount(2);
});

test("edits a comment in place with Edit and Save", async ({ page }) => {
  await post(page, "Typo here");
  await page.getByRole("button", { name: "Edit comment #1" }).click();
  await page.getByLabel("New text for comment #1").fill("Fixed text");
  await page.getByRole("button", { name: "Save comment #1" }).click();

  await expect(page.getByText("#1 Fixed text")).toBeVisible();
  await expect(page.getByText("Typo here")).toHaveCount(0);
  await expect(page.getByLabel("New text for comment #1")).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
});

test("deleting asks for confirmation; dismissing keeps the comment", async ({ page }) => {
  await post(page, "Keep me");
  const messages = [];
  page.once("dialog", (dialog) => {
    messages.push(dialog.message());
    dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete comment #1" }).click();
  await expect.poll(() => messages).toEqual(["Delete this comment?"]);
  await expect(page.getByText("#1 Keep me")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(page.getByText("#1 Keep me")).toBeVisible();
});

test("accepting the dialog deletes the comment", async ({ page }) => {
  await post(page, "Remove me");
  await post(page, "Stay");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete comment #1" }).click();

  await expect(page.getByText("Remove me")).toHaveCount(0);
  await expect(page.getByText("#2 Stay")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
});

test("deleting a comment also removes its replies from the count", async ({ page }) => {
  await post(page, "Parent");
  await reply(page, 1, "Child");
  await expect(page.locator("#cm-count")).toHaveText("2 comments");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete comment #1" }).click();
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
  await expect(page.getByText("Child")).toHaveCount(0);
});

test("comments, replies, edits and deletions survive a reload", async ({ page }) => {
  await post(page, "Alpha");
  await post(page, "Beta");
  await reply(page, 1, "Reply to alpha");
  await page.getByRole("button", { name: "Edit comment #2" }).click();
  await page.getByLabel("New text for comment #2").fill("Beta edited");
  await page.getByRole("button", { name: "Save comment #2" }).click();
  await expect(page.getByText("#2 Beta edited")).toBeVisible();

  await post(page, "Gone");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete comment #4" }).click();
  await expect(page.getByText("Gone")).toHaveCount(0);

  await page.reload();
  await expect(page.locator("#cm-count")).toHaveText("3 comments");
  await expect(page.getByRole("list", { name: "Replies to comment #1" }).getByText("#3 Reply to alpha")).toBeVisible();
  await expect(page.getByText("#2 Beta edited")).toBeVisible();
  await expect(page.getByText("Gone")).toHaveCount(0);
});

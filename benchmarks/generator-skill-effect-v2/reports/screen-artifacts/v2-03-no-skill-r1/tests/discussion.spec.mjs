import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("0 comments")).toBeVisible();
});

async function post(page, text) {
  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post" }).click();
}

async function reply(page, id, text) {
  await page.getByRole("button", { name: `Reply to comment #${id}` }).click();
  await post(page, text);
}

test("posts a comment and keeps it after reload", async ({ page }) => {
  await post(page, "Hello world");
  const thread = page.getByRole("list", { name: "Comments" });
  await expect(thread.getByText("#1 Hello world")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
  await expect(page.getByLabel("Your comment")).toHaveValue("");

  await page.reload();
  await expect(thread.getByText("#1 Hello world")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
});

test("does not post an empty comment", async ({ page }) => {
  await post(page, "   ");
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
  await expect(page.locator(".comment")).toHaveCount(0);
});

test("nests a reply under the comment it answers, not another one", async ({ page }) => {
  await post(page, "First");
  await post(page, "Second");
  await reply(page, 2, "Reply to second");

  const second = page.locator('li.comment[data-id="2"]');
  const first = page.locator('li.comment[data-id="1"]');
  await expect(second.getByRole("list", { name: "Replies to comment #2" }).getByText("#3 Reply to second")).toBeVisible();
  await expect(first.getByText("Reply to second")).toHaveCount(0);
  await expect(first.getByRole("list")).toHaveCount(0);

  await page.reload();
  await expect(page.locator('li.comment[data-id="2"]').getByRole("list", { name: "Replies to comment #2" }).getByText("#3 Reply to second")).toBeVisible();
  await expect(page.locator('li.comment[data-id="1"]').getByText("Reply to second")).toHaveCount(0);
});

test("counter includes replies", async ({ page }) => {
  await post(page, "Top");
  await reply(page, 1, "Child A");
  await expect(page.locator("#cm-count")).toHaveText("2 comments");
  await reply(page, 1, "Child B");
  await expect(page.locator("#cm-count")).toHaveText("3 comments");

  await page.reload();
  await expect(page.locator("#cm-count")).toHaveText("3 comments");
});

test("edits a comment in place with Edit and Save", async ({ page }) => {
  await post(page, "Original");
  await post(page, "Other");
  await page.getByRole("button", { name: "Edit comment #1" }).click();
  await page.getByLabel("New text for comment #1").fill("Changed");
  await page.getByRole("button", { name: "Save comment #1" }).click();

  const first = page.locator('li.comment[data-id="1"]');
  await expect(first.locator(".text")).toHaveText("#1 Changed");
  await expect(page.getByText("Original")).toHaveCount(0);
  await expect(page.locator('li.comment[data-id="2"] .text')).toHaveText("#2 Other");
  await expect(page.locator("li.comment")).toHaveCount(2);

  await page.reload();
  await expect(page.locator('li.comment[data-id="1"] .text')).toHaveText("#1 Changed");
});

test("edits a reply and keeps it nested", async ({ page }) => {
  await post(page, "Parent");
  await reply(page, 1, "Child");
  await page.getByRole("button", { name: "Edit comment #2" }).click();
  await page.getByLabel("New text for comment #2").fill("Child edited");
  await page.getByRole("button", { name: "Save comment #2" }).click();

  const replies = page.getByRole("list", { name: "Replies to comment #1" });
  await expect(replies.getByText("#2 Child edited")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("2 comments");
});

test("deletes a comment after accepting the confirm dialog", async ({ page }) => {
  await post(page, "Keep me");
  await post(page, "Remove me");

  const messages = [];
  page.once("dialog", (dialog) => {
    messages.push(dialog.message());
    return dialog.accept();
  });
  await page.getByRole("button", { name: "Delete comment #2" }).click();

  await expect(page.getByText("Remove me")).toHaveCount(0);
  await expect(page.getByText("#1 Keep me")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
  expect(messages).toEqual(["Delete this comment?"]);

  await page.reload();
  await expect(page.getByText("Remove me")).toHaveCount(0);
  await expect(page.getByText("#1 Keep me")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
});

test("keeps the comment when the confirm dialog is dismissed", async ({ page }) => {
  await post(page, "Stay");

  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Delete comment #1" }).click();

  await expect(page.getByText("#1 Stay")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(page.getByText("#1 Stay")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
});

test("deleting a comment also removes its replies and updates the counter", async ({ page }) => {
  await post(page, "Parent");
  await reply(page, 1, "Child");
  await post(page, "Sibling");
  await expect(page.locator("#cm-count")).toHaveText("3 comments");

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete comment #1" }).click();

  await expect(page.getByText("Parent")).toHaveCount(0);
  await expect(page.getByText("Child")).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(page.locator("li.comment")).toHaveCount(1);
  await expect(page.getByText("#3 Sibling")).toBeVisible();
});

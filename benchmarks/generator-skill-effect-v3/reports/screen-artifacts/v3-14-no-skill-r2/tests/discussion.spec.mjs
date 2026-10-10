import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
});

async function post(page, text) {
  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post" }).click();
  await expect(page.getByLabel("Your comment")).toHaveValue("");
  await expect(page.getByLabel("Your comment")).toBeEnabled();
}

async function reply(page, id, text) {
  await page.getByRole("button", { name: `Reply to comment #${id}` }).click();
  await post(page, text);
}

test("posts a comment and keeps it after reload", async ({ page }) => {
  await post(page, "Hello world");
  const thread = page.getByRole("list", { name: "Comments", exact: true });
  await expect(thread.getByText("#1 Hello world")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(thread.getByText("#1 Hello world")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
});

test("reply nests under the chosen comment and counts toward the total", async ({ page }) => {
  await post(page, "First");
  await post(page, "Second");
  await reply(page, 2, "Reply to second");
  await reply(page, 1, "Reply to first");

  await expect(page.locator("#cm-count")).toHaveText("4 comments");
  const first = page.locator('li.comment[data-id="1"]');
  const second = page.locator('li.comment[data-id="2"]');
  await expect(second.getByRole("list", { name: "Replies to comment #2" }).getByText("Reply to second")).toBeVisible();
  await expect(first.getByRole("list", { name: "Replies to comment #1" }).getByText("Reply to first")).toBeVisible();
  await expect(first.getByText("Reply to second")).toHaveCount(0);
  await expect(second.getByText("Reply to first")).toHaveCount(0);

  await page.reload();
  await expect(page.locator("#cm-count")).toHaveText("4 comments");
  await expect(page.locator('li.comment[data-id="2"]').getByRole("list", { name: "Replies to comment #2" }).getByText("Reply to second")).toBeVisible();
});

test("counter reads 3 comments with a comment and two replies", async ({ page }) => {
  await post(page, "Root");
  await reply(page, 1, "Child A");
  await reply(page, 1, "Child B");
  await expect(page.locator("#cm-count")).toHaveText("3 comments");
});

test("edits a comment in place and persists it", async ({ page }) => {
  await post(page, "Original");
  await page.getByRole("button", { name: "Edit comment #1" }).click();
  await page.getByLabel("New text for comment #1").fill("Changed");
  await page.getByRole("button", { name: "Save comment #1" }).click();

  await expect(page.getByText("#1 Changed")).toBeVisible();
  await expect(page.getByText("Original")).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(page.getByText("#1 Changed")).toBeVisible();
});

test("editing a reply keeps it nested under its parent", async ({ page }) => {
  await post(page, "Parent");
  await reply(page, 1, "Child");
  await page.getByRole("button", { name: "Edit comment #2" }).click();
  await page.getByLabel("New text for comment #2").fill("Child edited");
  await page.getByRole("button", { name: "Save comment #2" }).click();

  await expect(
    page.getByRole("list", { name: "Replies to comment #1" }).getByText("#2 Child edited"),
  ).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("2 comments");
});

test("dismissing the delete dialog keeps the comment", async ({ page }) => {
  await post(page, "Keep me");
  let message;
  page.once("dialog", (dialog) => {
    message = dialog.message();
    return dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete comment #1" }).click();

  await expect.poll(() => message).toBe("Delete this comment?");
  await expect(page.getByText("#1 Keep me")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(page.getByText("#1 Keep me")).toBeVisible();
});

test("accepting the delete dialog removes the comment for good", async ({ page }) => {
  await post(page, "Remove me");
  await post(page, "Stay");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete comment #1" }).click();

  await expect(page.getByText("Remove me")).toHaveCount(0);
  await expect(page.getByText("#2 Stay")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(page.getByText("Remove me")).toHaveCount(0);
  await expect(page.getByText("#2 Stay")).toBeVisible();
});

test("deleting a reply leaves its parent and updates the counter", async ({ page }) => {
  await post(page, "Parent");
  await reply(page, 1, "Child");
  await expect(page.locator("#cm-count")).toHaveText("2 comments");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete comment #2" }).click();

  await expect(page.getByText("Child")).toHaveCount(0);
  await expect(page.getByText("#1 Parent")).toBeVisible();
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
});

test("deleting a comment also removes its replies", async ({ page }) => {
  await post(page, "Parent");
  await reply(page, 1, "Child");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete comment #1" }).click();

  await expect(page.locator("#cm-count")).toHaveText("0 comments");
  await page.reload();
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
});

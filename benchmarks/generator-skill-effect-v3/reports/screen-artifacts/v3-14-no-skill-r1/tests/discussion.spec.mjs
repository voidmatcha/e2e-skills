import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
});

async function post(page, text) {
  const responded = page.waitForResponse((r) => r.url().endsWith("/api/comments") && r.request().method() === "POST");
  await page.getByLabel("Your comment").fill(text);
  await page.getByRole("button", { name: "Post" }).click();
  await responded;
}

const comment = (page, id) => page.locator(`li.comment[data-id="${id}"]`);

test("posts a comment and keeps it after reload", async ({ page }) => {
  await post(page, "Hello world");
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
  await expect(comment(page, 1).locator("> .text")).toHaveText("#1 Hello world");
  await expect(page.getByLabel("Your comment")).toHaveValue("");

  await page.reload();
  await expect(comment(page, 1).locator("> .text")).toHaveText("#1 Hello world");
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
});

test("reply nests under the chosen comment and counts toward the total", async ({ page }) => {
  await post(page, "First");
  await post(page, "Second");
  await page.getByRole("button", { name: "Reply to comment #2" }).click();
  await post(page, "Answer to second");

  await expect(page.locator("#cm-count")).toHaveText("3 comments");
  const replies = page.getByRole("list", { name: "Replies to comment #2" });
  await expect(replies.locator("li.comment")).toHaveCount(1);
  await expect(replies.locator(".text")).toHaveText("#3 Answer to second");
  await expect(page.getByRole("list", { name: "Replies to comment #1" })).toHaveCount(0);
  await expect(comment(page, 1).locator(".replies")).toHaveCount(0);

  await page.reload();
  await expect(page.getByRole("list", { name: "Replies to comment #2" }).locator(".text")).toHaveText("#3 Answer to second");
  await expect(page.locator("#cm-count")).toHaveText("3 comments");
});

test("edits a comment in place and persists the change", async ({ page }) => {
  await post(page, "Original");
  await post(page, "Other");
  await page.getByRole("button", { name: "Edit comment #1" }).click();
  await page.getByLabel("New text for comment #1").fill("Changed");
  const saved = page.waitForResponse((r) => r.request().method() === "PATCH");
  await page.getByRole("button", { name: "Save comment #1" }).click();
  await saved;

  await expect(comment(page, 1).locator("> .text")).toHaveText("#1 Changed");
  await expect(comment(page, 2).locator("> .text")).toHaveText("#2 Other");
  await expect(page.locator("#cm-count")).toHaveText("2 comments");

  await page.reload();
  await expect(comment(page, 1).locator("> .text")).toHaveText("#1 Changed");
});

test("deleting after accepting the dialog removes the comment for good", async ({ page }) => {
  await post(page, "Keep me");
  await post(page, "Remove me");
  const messages = [];
  page.once("dialog", (dialog) => {
    messages.push(dialog.message());
    dialog.accept();
  });
  const deleted = page.waitForResponse((r) => r.request().method() === "DELETE");
  await page.getByRole("button", { name: "Delete comment #2" }).click();
  await deleted;

  expect(messages).toEqual(["Delete this comment?"]);
  await expect(comment(page, 2)).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("1 comment");

  await page.reload();
  await expect(comment(page, 1)).toHaveCount(1);
  await expect(comment(page, 2)).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
});

test("dismissing the delete dialog keeps the comment", async ({ page }) => {
  await post(page, "Still here");
  let seen = 0;
  page.once("dialog", (dialog) => {
    seen++;
    dialog.dismiss();
  });
  await page.getByRole("button", { name: "Delete comment #1" }).click();
  await expect.poll(() => seen).toBe(1);

  await expect(comment(page, 1).locator("> .text")).toHaveText("#1 Still here");
  await expect(page.locator("#cm-count")).toHaveText("1 comment");
  await page.reload();
  await expect(comment(page, 1).locator("> .text")).toHaveText("#1 Still here");
});

test("deleting a comment also removes its replies from the count", async ({ page }) => {
  await post(page, "Parent");
  await page.getByRole("button", { name: "Reply to comment #1" }).click();
  await post(page, "Child");
  await expect(page.locator("#cm-count")).toHaveText("2 comments");

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete comment #1" }).click();
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
  await page.reload();
  await expect(page.locator("li.comment")).toHaveCount(0);
  await expect(page.locator("#cm-count")).toHaveText("0 comments");
});

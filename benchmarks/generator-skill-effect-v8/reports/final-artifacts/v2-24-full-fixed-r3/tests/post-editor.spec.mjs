import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
});

test("autosaves the draft and restores it after reload", async ({ page }) => {
  const titleInput = page.getByLabel("Title");
  const bodyInput = page.getByLabel("Body");
  const status = page.getByRole("status");
  const title = "Autosaved title";
  const body = "Body text saved after typing stops.";

  const draftRequestPromise = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "PUT" && url.pathname === "/api/draft";
  });

  await titleInput.fill(title);
  await bodyInput.fill(body);

  const draftRequest = await draftRequestPromise;
  expect(draftRequest.postDataJSON()).toEqual({ title, body });
  await expect(status).toHaveText("Draft saved");

  await page.reload();
  await expect(titleInput).toHaveValue(title);
  await expect(bodyInput).toHaveValue(body);
});

test("publishes the post, empties the editor, and clears the draft", async ({ page }) => {
  const titleInput = page.getByLabel("Title");
  const bodyInput = page.getByLabel("Body");
  const status = page.getByRole("status");
  const publishedPosts = page.getByRole("list", { name: "Published posts", exact: true });
  const title = "Published title";
  const body = "Published body.";

  await titleInput.fill(title);
  await bodyInput.fill(body);
  await expect(status).toHaveText("Draft saved");

  const publishRequestPromise = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "POST" && url.pathname === "/api/posts";
  });

  await page.getByRole("button", { name: "Publish", exact: true }).click();

  const publishRequest = await publishRequestPromise;
  expect(publishRequest.postDataJSON()).toEqual({ title, body });
  await expect(publishedPosts.getByRole("listitem").filter({ hasText: /^Published title$/ })).toBeVisible();
  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");

  await page.reload();
  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");
});

test("discards the draft and clears it after reload", async ({ page }) => {
  const titleInput = page.getByLabel("Title");
  const bodyInput = page.getByLabel("Body");
  const status = page.getByRole("status");

  await titleInput.fill("Discarded title");
  await bodyInput.fill("Discarded body.");
  await expect(status).toHaveText("Draft saved");

  const discardRequestPromise = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "DELETE" && url.pathname === "/api/draft";
  });

  await page.getByRole("button", { name: "Discard draft", exact: true }).click();

  await discardRequestPromise;
  await expect(status).toHaveText("Draft discarded");
  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");

  await page.reload();
  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");
});

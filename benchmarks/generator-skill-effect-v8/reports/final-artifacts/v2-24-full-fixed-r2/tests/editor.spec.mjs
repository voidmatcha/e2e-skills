import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("autosaves the draft and restores it after reload", async ({ page }) => {
  await page.goto("/");

  const titleInput = page.getByRole("textbox", { name: "Title", exact: true });
  const bodyInput = page.getByRole("textbox", { name: "Body", exact: true });
  const status = page.getByRole("status");
  const draftRequest = page.waitForRequest((request) =>
    request.method() === "PUT" && request.url().endsWith("/api/draft")
  );

  await titleInput.fill("Autosaved title");
  await bodyInput.fill("Autosaved body");

  const request = await draftRequest;
  expect(request.postDataJSON()).toEqual({
    title: "Autosaved title",
    body: "Autosaved body",
  });
  await expect(status).toHaveText("Draft saved");

  await page.reload();

  await expect(titleInput).toHaveValue("Autosaved title");
  await expect(bodyInput).toHaveValue("Autosaved body");
});

test("publishes the post and clears the stored draft", async ({ page }) => {
  await page.goto("/");

  const titleInput = page.getByRole("textbox", { name: "Title", exact: true });
  const bodyInput = page.getByRole("textbox", { name: "Body", exact: true });
  const publishedPosts = page.getByRole("list", {
    name: "Published posts",
    exact: true,
  });
  const publishRequest = page.waitForRequest((request) =>
    request.method() === "POST" && request.url().endsWith("/api/posts")
  );

  await titleInput.fill("Published title");
  await bodyInput.fill("Published body");
  await page.getByRole("button", { name: "Publish", exact: true }).click();

  const request = await publishRequest;
  expect(request.postDataJSON()).toEqual({
    title: "Published title",
    body: "Published body",
  });
  await expect(
    publishedPosts.getByRole("listitem").filter({ hasText: "Published title" })
  ).toBeVisible();
  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");

  await page.reload();

  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");
});

test("discards the draft and clears it after reload", async ({ page }) => {
  await page.goto("/");

  const titleInput = page.getByRole("textbox", { name: "Title", exact: true });
  const bodyInput = page.getByRole("textbox", { name: "Body", exact: true });
  const status = page.getByRole("status");

  const saveRequest = page.waitForRequest((request) =>
    request.method() === "PUT" && request.url().endsWith("/api/draft")
  );
  await titleInput.fill("Discarded title");
  await bodyInput.fill("Discarded body");
  await saveRequest;
  await expect(status).toHaveText("Draft saved");

  const discardRequest = page.waitForRequest((request) =>
    request.method() === "DELETE" && request.url().endsWith("/api/draft")
  );
  await page
    .getByRole("button", { name: "Discard draft", exact: true })
    .click();
  await discardRequest;

  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");

  await page.reload();

  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");
});

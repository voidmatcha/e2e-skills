import { expect, test } from "@playwright/test";

const draftPayload = async (request) => request.postDataJSON();

test.beforeEach(async ({ page, request }) => {
  const reset = await request.post("/api/reset");
  if (!reset.ok()) throw new Error(`Reset failed with ${reset.status()}`);
  await page.goto("/");
});

test("autosaves the draft and restores it after reload", async ({ page }) => {
  const titleInput = page.getByLabel("Title");
  const bodyInput = page.getByLabel("Body");
  const status = page.getByRole("status");

  const draftRequest = page.waitForRequest((request) => {
    return request.method() === "PUT" && new URL(request.url()).pathname === "/api/draft";
  });

  await titleInput.fill("Autosaved title");
  await bodyInput.fill("Autosaved body");

  const request = await draftRequest;
  expect(await draftPayload(request)).toEqual({
    title: "Autosaved title",
    body: "Autosaved body",
  });
  await expect(status).toHaveText("Draft saved");

  await page.reload();

  await expect(titleInput).toHaveValue("Autosaved title");
  await expect(bodyInput).toHaveValue("Autosaved body");
});

test("publishes the post and clears the stored draft", async ({ page }) => {
  const titleInput = page.getByLabel("Title");
  const bodyInput = page.getByLabel("Body");
  const publishedPosts = page.getByRole("list", { name: "Published posts", exact: true });
  const publishButton = page.getByRole("button", { name: "Publish", exact: true });

  await titleInput.fill("Published title");
  await bodyInput.fill("Published body");

  const publishRequest = page.waitForRequest((request) => {
    return request.method() === "POST" && new URL(request.url()).pathname === "/api/posts";
  });
  await publishButton.click();

  const request = await publishRequest;
  expect(await draftPayload(request)).toEqual({
    title: "Published title",
    body: "Published body",
  });
  await expect(publishedPosts.getByText("Published title")).toBeVisible();
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
  const discardButton = page.getByRole("button", { name: "Discard draft", exact: true });

  const draftRequest = page.waitForRequest((request) => {
    return request.method() === "PUT" && new URL(request.url()).pathname === "/api/draft";
  });
  await titleInput.fill("Discarded title");
  await bodyInput.fill("Discarded body");
  await draftRequest;
  await expect(status).toHaveText("Draft saved");

  const discardRequest = page.waitForRequest((request) => {
    return request.method() === "DELETE" && new URL(request.url()).pathname === "/api/draft";
  });
  await discardButton.click();
  await discardRequest;

  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");

  await page.reload();

  await expect(titleInput).toHaveValue("");
  await expect(bodyInput).toHaveValue("");
});

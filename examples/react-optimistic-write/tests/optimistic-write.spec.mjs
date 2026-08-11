import { expect, test } from "@playwright/test";

test.beforeEach(async ({ context, request }, testInfo) => {
  const { baseURL } = testInfo.project.use;
  if (typeof baseURL !== "string") {
    throw new Error("Playwright project baseURL must be configured");
  }
  const appOrigin = new URL(baseURL).origin;

  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (
      ["http:", "https:"].includes(url.protocol) &&
      (url.origin !== appOrigin || url.username || url.password)
    ) {
      await route.abort();
      return;
    }
    await route.continue();
  });

  const reset = await request.post("/api/reset");
  expect(reset.status()).toBe(204);
});

test.afterEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("sends exactly one like write before accepting optimistic success", async ({
  page,
}) => {
  // Given: the disposable server state is reset and the React control is ready.
  const faultQuery =
    process.env.DEMO_FAULT_MODE === "omit-post" ? "?fault=omit-post" : "";
  await page.goto(`/${faultQuery}`);
  const likeButton = page.getByRole("button", {
    name: "Like article",
    exact: true,
  });
  await expect(likeButton).toBeEnabled();

  const writes = [];
  page.on("request", (candidate) => {
    const url = new URL(candidate.url());
    if (candidate.method() === "POST" && url.pathname === "/api/like") {
      writes.push(candidate);
    }
  });
  const request = page.waitForRequest(
    (candidate) =>
      candidate.method() === "POST" &&
      new URL(candidate.url()).pathname === "/api/like",
    { timeout: 3_000 },
  );

  // When: the user likes the article.
  await likeButton.click();
  const write = await request;

  // Then: the write happened once and the optimistic state is accepted.
  expect(write.postDataJSON()).toEqual({ liked: true });
  await expect.poll(() => writes.length).toBe(1);
  await expect(likeButton).toHaveAttribute("aria-pressed", "true");
});

test("persists the confirmed write across a reload", async ({ page }) => {
  // Given: the normal page is ready with reset server state.
  await page.goto("/");
  const likeButton = page.getByRole("button", {
    name: "Like article",
    exact: true,
  });
  await expect(likeButton).toBeEnabled();
  const response = page.waitForResponse(
    (candidate) =>
      candidate.request().method() === "POST" &&
      new URL(candidate.url()).pathname === "/api/like" &&
      candidate.status() === 200,
  );

  // When: the user likes the article and the server confirms it.
  await likeButton.click();
  await response;
  await page.reload();

  // Then: a fresh React load reads the persisted server truth.
  await expect(likeButton).toBeEnabled();
  await expect(likeButton).toHaveAttribute("aria-pressed", "true");
});

test("rolls the optimistic state back when the write is rejected", async ({
  page,
}) => {
  // Given: the demo server is configured to reject the write.
  await page.goto("/?fault=reject-post");
  const likeButton = page.getByRole("button", {
    name: "Like article",
    exact: true,
  });
  const rollbackAlert = page.getByRole("alert");
  await expect(likeButton).toBeEnabled();
  const response = page.waitForResponse(
    (candidate) =>
      candidate.request().method() === "POST" &&
      new URL(candidate.url()).pathname === "/api/like",
  );

  // When: the user likes the article and the server rejects the write.
  await likeButton.click();
  const rejectedWrite = await response;

  // Then: false success is not retained.
  expect(rejectedWrite.status()).toBe(503);
  await expect(rollbackAlert).toHaveText(
    "Write failed. Optimistic state rolled back.",
  );
  await expect(likeButton).toHaveAttribute("aria-pressed", "false");
});

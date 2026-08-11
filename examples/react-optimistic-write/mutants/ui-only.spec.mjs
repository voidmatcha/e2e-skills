import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const reset = await request.post("/api/reset");
  expect(reset.status()).toBe(204);
});

test.afterEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("looks successful even when the POST is omitted", async ({ page }) => {
  // INTENTIONALLY_WEAK: this executable counterexample is excluded from the
  // default suite. e2e-reviewer should report #22 for this UI-only proof.
  // Given: the app will update local state but omit its write.
  await page.goto("/?fault=omit-post");
  const likeButton = page.getByRole("button", {
    name: "Like article",
    exact: true,
  });
  await expect(likeButton).toBeEnabled();

  // When: the user likes the article.
  await likeButton.click();

  // Then: the UI-only assertion stays green despite missing persistence.
  await expect(likeButton).toHaveAttribute("aria-pressed", "true");
});

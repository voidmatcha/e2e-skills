import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  expect((await request.post("/api/reset")).status()).toBe(204);
});

test("like shows Liked", async ({ page }) => {
  // INTENTIONALLY_WEAK: teaching example. This UI-only test asserts pixels only,
  // so it stays green when ./break-post.sh removes the POST (reviewer pattern #22).
  await page.goto("/");
  const like = page.getByRole("button", { name: "Like article" });
  await expect(like).toBeEnabled();
  await like.click();
  await expect(like).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".likes")).toHaveText("129 likes");
  await expect(page.getByRole("status")).toHaveText("Liked!");
});

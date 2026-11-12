import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  expect((await request.post("/api/reset")).status()).toBe(204);
});

test("like sends POST /api/like", async ({ page }) => {
  await page.goto("/");
  const like = page.getByRole("button", { name: "Like article" });
  await expect(like).toBeEnabled();
  const post = page.waitForRequest(
    (request) => request.method() === "POST" && new URL(request.url()).pathname === "/api/like",
    { timeout: 3000 },
  );
  await like.click();
  await post;
  await expect(like).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".likes")).toHaveText("129 likes");
});

import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  expect((await request.post("/api/reset")).status()).toBe(204);
});

test("rejected like: restores the heart and count and explains the error", async ({ page, request }) => {
  await page.goto("/");
  const like = page.getByRole("button", { name: "Like article" });
  await expect(like).toBeEnabled();
  expect((await request.post("/api/fail-next")).status()).toBe(200);
  const rejected = page.waitForResponse(
    (response) => response.request().method() === "POST" && new URL(response.url()).pathname === "/api/like",
  );
  await like.click();
  expect((await rejected).status()).toBe(500);
  await expect(like, "rolls back rejected like").toHaveAttribute("aria-pressed", "false");
  await expect(page.locator(".likes")).toHaveText("128 likes");
  await expect(page.getByRole("alert")).toHaveText("Couldn't save. Try again.");
});

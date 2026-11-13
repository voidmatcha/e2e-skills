import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  expect((await request.post("/api/reset")).status()).toBe(204);
});

test("happy path: like fills the heart and updates the count", async ({ page }) => {
  await page.goto("/");
  const like = page.getByRole("button", { name: "Like article" });
  await expect(like).toBeEnabled();
  const saved = page.waitForResponse(
    (response) => response.request().method() === "POST" && new URL(response.url()).pathname === "/api/like",
  );
  await like.click();
  expect((await saved).status()).toBe(200);
  await expect(like).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".likes")).toHaveText("129 likes");
  await expect(page.getByRole("status")).toHaveText("Liked!");
});

import { expect, test } from "@playwright/test";

test("persists the liked state after saving and reloading", async ({ page }) => {
  // Given: the article starts unliked in fresh disposable server state
  await page.goto("/");

  const likeButton = page.getByRole("button", {
    name: "Like article",
    exact: true,
  });

  await expect(likeButton).toBeEnabled();
  await expect(likeButton).toHaveAttribute("aria-pressed", "false");

  const likeRequests = [];
  page.on("request", (request) => {
    const url = new URL(request.url());

    if (request.method() === "POST" && url.pathname === "/api/like") {
      likeRequests.push(request);
    }
  });

  // When: the user likes the article and the save settles
  await likeButton.click();
  await expect(
    page.getByText("Saved on server.", { exact: true }),
  ).toBeVisible();
  await page.reload();

  // Then: fresh server truth still reports the article as liked
  await expect(likeButton).toHaveAttribute("aria-pressed", "true");

  // And: exactly one browser-originated like write carried the expected JSON
  expect(likeRequests).toHaveLength(1);
  expect(likeRequests[0].headers()["content-type"]).toContain(
    "application/json",
  );
  expect(likeRequests[0].postDataJSON()).toEqual({ liked: true });
});
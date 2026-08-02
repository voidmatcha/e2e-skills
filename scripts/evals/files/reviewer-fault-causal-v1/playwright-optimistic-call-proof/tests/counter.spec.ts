import { expect, test } from "@playwright/test";

test("increments the counter", async ({ page }) => {
  await page.goto("/counter");
  await page.getByRole("button", { name: "Increment" }).click();
  await expect(page.getByRole("status")).toHaveText("Count: 1");
});

test("sends the increment request", async ({ page }) => {
  await page.goto("/counter");
  const request = page.waitForRequest(
    (candidate) =>
      candidate.url().endsWith("/api/increment") &&
      candidate.method() === "POST",
  );
  await page.getByRole("button", { name: "Increment" }).click();
  await request;
});

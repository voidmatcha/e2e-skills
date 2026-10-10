import { expect, test } from "@playwright/test";

// Deliberately shallow and id-based: it exists as a sanity floor and must fail the markup refactor; never shown to a model.
test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds spending", async ({ page }) => {
  await page.fill("#bg-envelopes .envelope:nth-child(1) .spend input", "60");
  await page.click("#bg-envelopes .envelope:nth-child(1) .spend button:nth-of-type(1)");
  await expect(page.locator("#bg-envelopes .envelope:nth-child(1) .amounts")).toHaveText("$180 of $300");
});

test("resets an envelope", async ({ page }) => {
  await page.click("#bg-envelopes .envelope:nth-child(2) .spend button:nth-of-type(2)");
  await expect(page.locator("#bg-envelopes .envelope:nth-child(2) .amounts")).toHaveText("$0 of $150");
});

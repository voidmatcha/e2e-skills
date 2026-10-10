import { expect, test } from "@playwright/test";

const seedOrder = ["Blue in Green", "So What", "Freddie Freeloader", "All Blues"];

const trackItems = (page) => page.getByRole("list", { name: "Tracks", exact: true }).getByRole("listitem");

async function expectTrackOrder(page, titles) {
  await expect(trackItems(page)).toContainText(titles);
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expectTrackOrder(page, seedOrder);
});

test("plays and stops a track from the seeded playlist", async ({ page }) => {
  await expect(page.getByText("Total 36:21")).toBeVisible();

  await page.getByRole("button", { name: "Play Blue in Green", exact: true }).click();
  const nowPlaying = page.getByText(/Now playing:\s*Blue in Green/);
  await expect(nowPlaying).toBeVisible();

  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect(nowPlaying).not.toBeVisible();
});

test("reorders tracks with move controls and keeps the order after reload", async ({ page }) => {
  const orderRequest = page.waitForRequest((request) => request.method() === "PUT" && request.url().endsWith("/api/order"));
  await page.getByRole("button", { name: "Move So What up", exact: true }).click();
  const request = await orderRequest;
  expect(request.postDataJSON()).toEqual({ order: [2, 1, 3, 4] });

  await expectTrackOrder(page, ["So What", "Blue in Green", "Freddie Freeloader", "All Blues"]);

  await page.reload();
  await expectTrackOrder(page, ["So What", "Blue in Green", "Freddie Freeloader", "All Blues"]);

  const secondOrderRequest = page.waitForRequest((request) => request.method() === "PUT" && request.url().endsWith("/api/order"));
  await page.getByRole("button", { name: "Move Blue in Green down", exact: true }).click();
  const secondRequest = await secondOrderRequest;
  expect(secondRequest.postDataJSON()).toEqual({ order: [2, 3, 1, 4] });

  await expectTrackOrder(page, ["So What", "Freddie Freeloader", "Blue in Green", "All Blues"]);
});

test("removes a track and updates the total duration", async ({ page }) => {
  await expect(page.getByText("Total 36:21")).toBeVisible();
  const freddieTrack = trackItems(page).filter({ hasText: "Freddie Freeloader" });
  await expect(freddieTrack).toHaveCount(1);

  const removeRequest = page.waitForRequest((request) => request.method() === "DELETE" && request.url().endsWith("/api/tracks/3"));
  await page.getByRole("button", { name: "Remove Freddie Freeloader", exact: true }).click();
  await removeRequest;

  await expect(trackItems(page)).toHaveCount(3);
  await expect(freddieTrack).toHaveCount(0);
  await expect(page.getByText("Total 26:32")).toBeVisible();
});

test("toggles repeat with aria-pressed and remembers it after reload", async ({ page }) => {
  const repeatButton = page.getByRole("button", { name: "Repeat", exact: true });
  await expect(repeatButton).toHaveAttribute("aria-pressed", "false");

  const repeatRequest = page.waitForRequest((request) => request.method() === "PATCH" && request.url().endsWith("/api/repeat"));
  await repeatButton.click();
  const request = await repeatRequest;
  expect(request.postDataJSON()).toEqual({ repeat: true });

  await expect(repeatButton).toHaveAttribute("aria-pressed", "true");

  await page.reload();
  await expect(page.getByRole("button", { name: "Repeat", exact: true })).toHaveAttribute("aria-pressed", "true");
});

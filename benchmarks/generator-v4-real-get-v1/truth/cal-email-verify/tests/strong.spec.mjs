import { expect, test } from "@playwright/test";

test("verification email links persist both writes and consume their tokens", async ({ page, request }) => {
  await request.post("/api/reset");
  const verificationGets = [];
  page.on("request", (req) => {
    if (new URL(req.url()).pathname === "/api/auth/verify-email") verificationGets.push(req);
  });
  await page.goto("/");
  await expect(page.getByText("Primary: Unverified")).toBeVisible();
  await expect(page.getByText("Secondary: Unverified")).toBeVisible();

  await page.getByRole("link", { name: "Verify primary email" }).click();
  await expect(page.getByRole("heading", { name: "Event types" })).toBeVisible();
  await page.goto("/");
  await expect(page.getByText("Primary: Verified")).toBeVisible();
  await expect(page.getByText("Secondary: Unverified")).toBeVisible();

  await page.getByRole("link", { name: "Verify secondary email" }).click();
  await expect(page.getByRole("heading", { name: "Account profile" })).toBeVisible();
  await expect(page.getByText("Primary: Verified")).toBeVisible();
  await expect(page.getByText("Secondary: Verified")).toBeVisible();
  expect(verificationGets.map((req) => [req.method(), new URL(req.url()).search]))
    .toEqual([["GET", "?token=primary-token"], ["GET", "?token=secondary-token"]]);

  const repeat = await request.get("/api/auth/verify-email?token=secondary-token", { maxRedirects: 0 });
  expect(repeat.status()).toBe(401);
  await page.goto("/settings/my-account/profile");
  await expect(page.getByText("Primary: Verified")).toBeVisible();
  await expect(page.getByText("Secondary: Verified")).toBeVisible();
});

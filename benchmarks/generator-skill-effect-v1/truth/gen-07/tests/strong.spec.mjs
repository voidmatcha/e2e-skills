import { expect, test } from "@playwright/test";

const email = (page) => page.getByLabel("Email address");
const subscribe = (page) => page.getByRole("button", { name: "Subscribe" }).click();

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByText("0 subscribers")).toBeVisible();
});

test("subscribes a new address and counts it", async ({ page }) => {
  await email(page).fill("ada@example.com");
  await subscribe(page);
  await expect(page.getByRole("status")).toHaveText("Thanks, you're subscribed");
  await expect(page.getByText("1 subscriber", { exact: true })).toBeVisible();
  await email(page).fill("grace@example.com");
  await subscribe(page);
  await expect(page.getByText("2 subscribers")).toBeVisible();
});

test("rejects an invalid address", async ({ page }) => {
  await email(page).fill("not-an-address");
  await subscribe(page);
  await expect(page.getByRole("alert")).toHaveText("Enter a valid email address");
  await expect(page.getByText("0 subscribers")).toBeVisible();
  await page.reload();
  await expect(page.getByText("0 subscribers")).toBeVisible();
});

test("rejects a duplicate address", async ({ page }) => {
  await email(page).fill("ada@example.com");
  await subscribe(page);
  await expect(page.getByRole("status")).toHaveText("Thanks, you're subscribed");
  await email(page).fill("ada@example.com");
  await subscribe(page);
  await expect(page.getByRole("alert")).toHaveText("That email is already subscribed");
  await expect(page.getByText("1 subscriber", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("1 subscriber", { exact: true })).toBeVisible();
});

test("enter submits like the button", async ({ page }) => {
  await email(page).fill("ada@example.com");
  await email(page).press("Enter");
  await expect(page.getByRole("status")).toHaveText("Thanks, you're subscribed");
  await expect(page.getByText("1 subscriber", { exact: true })).toBeVisible();
});

test("clears the field after success", async ({ page }) => {
  await email(page).fill("ada@example.com");
  await subscribe(page);
  await expect(page.getByRole("status")).toHaveText("Thanks, you're subscribed");
  await expect(email(page)).toHaveValue("");
});

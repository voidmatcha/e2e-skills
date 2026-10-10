import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  // the initial count is fetched asynchronously; wait for it before interacting
  await expect(page.locator("#nl-count")).toHaveText("0 subscribers");
});

const email = (page) => page.getByLabel("Email address");
const subscribe = (page) => page.getByRole("button", { name: "Subscribe" });
const count = (page) => page.locator("#nl-count");

test("subscribes a new address and updates the count", async ({ page }) => {
  await email(page).fill("first@example.com");
  await subscribe(page).click();
  await expect(page.getByText("Thanks, you're subscribed")).toBeVisible();
  await expect(count(page)).toHaveText("1 subscriber");

  await email(page).fill("second@example.com");
  await subscribe(page).click();
  await expect(count(page)).toHaveText("2 subscribers");
});

test("rejects an invalid address without counting it", async ({ page }) => {
  await email(page).fill("not-an-email");
  await subscribe(page).click();
  await expect(page.getByRole("alert")).toHaveText("Enter a valid email address");
  await expect(page.getByText("Thanks, you're subscribed")).toBeHidden();
  await expect(count(page)).toHaveText("0 subscribers");
  await page.reload();
  await expect(count(page)).toHaveText("0 subscribers");
});

test("rejects a duplicate address without counting it twice", async ({ page }) => {
  await email(page).fill("dupe@example.com");
  await subscribe(page).click();
  await expect(count(page)).toHaveText("1 subscriber");

  await email(page).fill("dupe@example.com");
  await subscribe(page).click();
  await expect(page.getByRole("alert")).toHaveText("That email is already subscribed");
  await expect(page.getByText("Thanks, you're subscribed")).toBeHidden();
  await expect(count(page)).toHaveText("1 subscriber");
  await page.reload();
  await expect(count(page)).toHaveText("1 subscriber");
});

test("pressing Enter submits like the Subscribe button", async ({ page }) => {
  await email(page).fill("enter@example.com");
  await email(page).press("Enter");
  await expect(page.getByText("Thanks, you're subscribed")).toBeVisible();
  await expect(count(page)).toHaveText("1 subscriber");

  await email(page).fill("bad");
  await email(page).press("Enter");
  await expect(page.getByRole("alert")).toHaveText("Enter a valid email address");

  await email(page).fill("enter@example.com");
  await email(page).press("Enter");
  await expect(page.getByRole("alert")).toHaveText("That email is already subscribed");
  await expect(count(page)).toHaveText("1 subscriber");
});

test("empties the email field after a successful subscription", async ({ page }) => {
  await email(page).fill("clear@example.com");
  await subscribe(page).click();
  await expect(page.getByText("Thanks, you're subscribed")).toBeVisible();
  await expect(email(page)).toHaveValue("");
});

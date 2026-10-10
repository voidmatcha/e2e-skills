import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBe(true);
  await page.goto("/");
  await expect(page.locator("#nl-count")).toHaveText("0 subscribers");
});

const emailField = (page) => page.getByLabel("Email address");
const subscribe = (page) => page.getByRole("button", { name: "Subscribe" });
const count = (page) => page.locator("#nl-count");
const success = (page) => page.getByText("Thanks, you're subscribed");

test("subscribing with a valid new email shows thanks and increments the count", async ({ page }) => {
  await emailField(page).fill("first@example.com");
  await subscribe(page).click();
  await expect(success(page)).toBeVisible();
  await expect(count(page)).toHaveText("1 subscriber");

  await emailField(page).fill("second@example.com");
  await subscribe(page).click();
  await expect(count(page)).toHaveText("2 subscribers");
  await expect(success(page)).toBeVisible();
});

test("an invalid email shows an error and is not counted", async ({ page }) => {
  await emailField(page).fill("not-an-email");
  await subscribe(page).click();
  await expect(page.getByText("Enter a valid email address")).toBeVisible();
  await expect(success(page)).toBeHidden();
  await expect(count(page)).toHaveText("0 subscribers");

  await page.reload();
  await expect(count(page)).toHaveText("0 subscribers");
});

test("an already subscribed email shows an error and is not counted twice", async ({ page }) => {
  await emailField(page).fill("dupe@example.com");
  await subscribe(page).click();
  await expect(count(page)).toHaveText("1 subscriber");

  await emailField(page).fill("dupe@example.com");
  await subscribe(page).click();
  await expect(page.getByText("That email is already subscribed")).toBeVisible();
  await expect(success(page)).toBeHidden();
  await expect(count(page)).toHaveText("1 subscriber");

  await page.reload();
  await expect(count(page)).toHaveText("1 subscriber");
});

test("pressing Enter in the email field submits like the Subscribe button", async ({ page }) => {
  await emailField(page).fill("enter@example.com");
  await emailField(page).press("Enter");
  await expect(success(page)).toBeVisible();
  await expect(count(page)).toHaveText("1 subscriber");

  await emailField(page).fill("bad");
  await emailField(page).press("Enter");
  await expect(page.getByText("Enter a valid email address")).toBeVisible();
  await expect(count(page)).toHaveText("1 subscriber");

  await emailField(page).fill("enter@example.com");
  await emailField(page).press("Enter");
  await expect(page.getByText("That email is already subscribed")).toBeVisible();
  await expect(count(page)).toHaveText("1 subscriber");
});

test("the email field is emptied after a successful subscription", async ({ page }) => {
  await emailField(page).fill("clear@example.com");
  await subscribe(page).click();
  await expect(success(page)).toBeVisible();
  await expect(emailField(page)).toHaveValue("");
});

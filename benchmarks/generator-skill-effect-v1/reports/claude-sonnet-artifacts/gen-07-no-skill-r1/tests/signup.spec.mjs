import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.locator("#nl-count")).toHaveText("0 subscribers");
});

const emailField = (page) => page.getByLabel("Email address");
const subscribe = (page) => page.getByRole("button", { name: "Subscribe" });
const count = (page) => page.locator("#nl-count");

test("subscribing with a new email shows thanks and increments the count", async ({ page }) => {
  await emailField(page).fill("a@example.com");
  await subscribe(page).click();
  await expect(page.getByText("Thanks, you're subscribed")).toBeVisible();
  await expect(count(page)).toHaveText("1 subscriber");

  await emailField(page).fill("b@example.com");
  await subscribe(page).click();
  await expect(count(page)).toHaveText("2 subscribers");
});

test("an invalid email shows an error and is not counted", async ({ page }) => {
  await emailField(page).fill("not-an-email");
  await subscribe(page).click();
  await expect(page.getByRole("alert")).toHaveText("Enter a valid email address");
  await expect(page.getByText("Thanks, you're subscribed")).toBeHidden();
  await expect(count(page)).toHaveText("0 subscribers");
});

test("a duplicate email shows an error and is not counted twice", async ({ page }) => {
  await emailField(page).fill("dup@example.com");
  await subscribe(page).click();
  await expect(count(page)).toHaveText("1 subscriber");

  await emailField(page).fill("dup@example.com");
  await subscribe(page).click();
  await expect(page.getByRole("alert")).toHaveText("That email is already subscribed");
  await expect(page.getByText("Thanks, you're subscribed")).toBeHidden();
  await expect(count(page)).toHaveText("1 subscriber");
});

test("pressing Enter submits like the Subscribe button", async ({ page }) => {
  await emailField(page).fill("enter@example.com");
  await emailField(page).press("Enter");
  await expect(page.getByText("Thanks, you're subscribed")).toBeVisible();
  await expect(count(page)).toHaveText("1 subscriber");

  await emailField(page).fill("enter@example.com");
  await emailField(page).press("Enter");
  await expect(page.getByRole("alert")).toHaveText("That email is already subscribed");

  await emailField(page).fill("bad");
  await emailField(page).press("Enter");
  await expect(page.getByRole("alert")).toHaveText("Enter a valid email address");
  await expect(count(page)).toHaveText("1 subscriber");
});

test("the email field is emptied after a successful subscription", async ({ page }) => {
  await emailField(page).fill("clear@example.com");
  await subscribe(page).click();
  await expect(page.getByText("Thanks, you're subscribed")).toBeVisible();
  await expect(emailField(page)).toHaveValue("");
});

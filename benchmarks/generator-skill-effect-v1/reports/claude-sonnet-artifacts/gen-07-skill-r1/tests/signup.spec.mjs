import { expect, test } from "@playwright/test";

test.describe("newsletter signup", () => {
  let emailInput;
  let subscribeButton;
  let count;

  test.beforeEach(async ({ page, request }) => {
    // The app keeps subscribers in memory; reset through the app's own test seam.
    const reset = await request.post("/api/reset");
    expect(reset.ok()).toBe(true);

    emailInput = page.getByLabel("Email address");
    subscribeButton = page.getByRole("button", { name: "Subscribe" });
    count = page.locator("#nl-count");

    await page.goto("/");
    // The count is filled in by the page's initial fetch; wait for it before interacting.
    await expect(count).toHaveText("0 subscribers");
  });

  test("subscribing with new emails shows thanks and raises the count", async ({ page }) => {
    const post = page.waitForRequest(
      (r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/subscribers",
    );
    await emailInput.fill("first@example.com");
    await subscribeButton.click();
    expect((await post).postDataJSON()).toEqual({ email: "first@example.com" });

    await expect(page.getByRole("status")).toHaveText("Thanks, you're subscribed");
    await expect(count).toHaveText("1 subscriber");

    await emailInput.fill("second@example.com");
    await subscribeButton.click();
    await expect(count).toHaveText("2 subscribers");
  });

  test("an invalid email shows an error and is not counted", async ({ page }) => {
    await emailInput.fill("not-an-email");
    await subscribeButton.click();

    await expect(page.getByRole("alert")).toHaveText("Enter a valid email address");
    await expect(page.getByRole("status")).toBeEmpty();

    // Re-read the stored count from the server rather than trusting the unchanged DOM.
    await page.reload();
    await expect(count).toHaveText("0 subscribers");
  });

  test("an already subscribed email shows an error and is not counted twice", async ({ page }) => {
    await emailInput.fill("dupe@example.com");
    await subscribeButton.click();
    await expect(count).toHaveText("1 subscriber");

    await emailInput.fill("dupe@example.com");
    await subscribeButton.click();
    await expect(page.getByRole("alert")).toHaveText("That email is already subscribed");

    await page.reload();
    await expect(count).toHaveText("1 subscriber");
  });

  test("pressing Enter submits like the Subscribe button", async ({ page }) => {
    const post = page.waitForRequest(
      (r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/subscribers",
    );
    await emailInput.fill("enter@example.com");
    await emailInput.press("Enter");
    expect((await post).postDataJSON()).toEqual({ email: "enter@example.com" });

    await expect(page.getByRole("status")).toHaveText("Thanks, you're subscribed");
    await expect(count).toHaveText("1 subscriber");
  });

  test("the email field is emptied after a successful subscription", async ({ page }) => {
    await emailInput.fill("clear@example.com");
    await subscribeButton.click();

    await expect(page.getByRole("status")).toHaveText("Thanks, you're subscribed");
    await expect(emailInput).toHaveValue("");
  });
});

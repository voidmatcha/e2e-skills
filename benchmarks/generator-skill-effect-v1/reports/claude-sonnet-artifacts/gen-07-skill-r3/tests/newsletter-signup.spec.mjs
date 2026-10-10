import { expect, test } from "@playwright/test";

const isSubscribe = (request) =>
  request.method() === "POST" && new URL(request.url()).pathname === "/api/subscribers";

test.describe("newsletter signup", () => {
  let emailInput;
  let subscribeButton;
  let subscriberCount;
  let successMessage;
  let errorMessage;

  test.beforeEach(async ({ page, request }) => {
    // The app keeps subscribers in memory; reset through the test seam so every test starts empty.
    const reset = await request.post("/api/reset");
    expect(reset.ok()).toBe(true);

    emailInput = page.getByLabel("Email address");
    subscribeButton = page.getByRole("button", { name: "Subscribe" });
    subscriberCount = page.getByText(/^\d+ subscribers?$/);
    successMessage = page.getByRole("status");
    errorMessage = page.getByRole("alert");

    await page.goto("/");
    // The count is fetched after load; wait for it so a late response cannot overwrite a later one.
    await expect(subscriberCount).toHaveText("0 subscribers");
  });

  test("subscribes a valid new email and updates the count", async ({ page }) => {
    const subscribeRequest = page.waitForRequest(isSubscribe);
    await emailInput.fill("ada@example.com");
    await subscribeButton.click();
    expect((await subscribeRequest).postDataJSON()).toEqual({ email: "ada@example.com" });

    await expect(subscriberCount).toHaveText("1 subscriber");
    await expect(successMessage).toHaveText("Thanks, you're subscribed");
    await expect(errorMessage).toBeEmpty();
  });

  test("counts each additional subscriber", async () => {
    await emailInput.fill("ada@example.com");
    await subscribeButton.click();
    await expect(subscriberCount).toHaveText("1 subscriber");

    await emailInput.fill("grace@example.com");
    await subscribeButton.click();

    await expect(subscriberCount).toHaveText("2 subscribers");
  });

  test("rejects an invalid email without counting it", async ({ page }) => {
    const subscribeResponse = page.waitForResponse((response) => isSubscribe(response.request()));
    await emailInput.fill("not-an-email");
    await subscribeButton.click();
    expect((await subscribeResponse).status()).toBe(400);

    await expect(errorMessage).toHaveText("Enter a valid email address");
    await expect(successMessage).toBeEmpty();

    // Re-read the stored count; the failed request does not refresh the visible one.
    await page.reload();
    await expect(subscriberCount).toHaveText("0 subscribers");
  });

  test("rejects an already subscribed email without counting it twice", async ({ page }) => {
    await emailInput.fill("ada@example.com");
    await subscribeButton.click();
    await expect(subscriberCount).toHaveText("1 subscriber");

    const subscribeResponse = page.waitForResponse((response) => isSubscribe(response.request()));
    await emailInput.fill("ada@example.com");
    await subscribeButton.click();
    expect((await subscribeResponse).status()).toBe(409);

    await expect(errorMessage).toHaveText("That email is already subscribed");
    await expect(successMessage).toBeEmpty();

    await page.reload();
    await expect(subscriberCount).toHaveText("1 subscriber");
  });

  test("submits with Enter exactly like the Subscribe button", async ({ page }) => {
    const subscribeRequest = page.waitForRequest(isSubscribe);
    await emailInput.fill("ada@example.com");
    await emailInput.press("Enter");
    expect((await subscribeRequest).postDataJSON()).toEqual({ email: "ada@example.com" });

    await expect(subscriberCount).toHaveText("1 subscriber");
    await expect(successMessage).toHaveText("Thanks, you're subscribed");
    await expect(emailInput).toHaveValue("");
  });

  test("empties the email field after a successful subscription", async () => {
    await emailInput.fill("ada@example.com");
    await subscribeButton.click();

    await expect(emailInput).toHaveValue("");
    await expect(successMessage).toHaveText("Thanks, you're subscribed");
  });
});

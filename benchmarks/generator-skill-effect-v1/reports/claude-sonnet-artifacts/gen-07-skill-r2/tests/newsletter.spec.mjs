import { expect, test } from "@playwright/test";

const isSubscribePost = (request) =>
  request.method() === "POST" && new URL(request.url()).pathname === "/api/subscribers";

test.describe("newsletter signup", () => {
  test.beforeEach(async ({ page, request }) => {
    // Disposable server state: every test starts with no subscribers.
    const reset = await request.post("/api/reset");
    expect(reset.ok()).toBe(true);
    await page.goto("/");
    // The count is filled in by the initial fetch; it is the page's ready signal.
    await expect(page.getByText("0 subscribers")).toBeVisible();
  });

  test("subscribing with new addresses shows the thanks message and grows the count", async ({ page }) => {
    const email = page.getByLabel("Email address");
    const subscribe = page.getByRole("button", { name: "Subscribe" });

    const firstCall = page.waitForRequest(isSubscribePost);
    await email.fill("first@example.com");
    await subscribe.click();
    expect((await firstCall).postDataJSON()).toEqual({ email: "first@example.com" });

    await expect(page.getByRole("status")).toHaveText("Thanks, you're subscribed");
    await expect(page.getByText("1 subscriber", { exact: true })).toBeVisible();

    await email.fill("second@example.com");
    await subscribe.click();
    await expect(page.getByText("2 subscribers")).toBeVisible();
  });

  test("an invalid address shows an error and is not counted", async ({ page }) => {
    const call = page.waitForRequest(isSubscribePost);
    await page.getByLabel("Email address").fill("not-an-email");
    await page.getByRole("button", { name: "Subscribe" }).click();
    expect((await call).postDataJSON()).toEqual({ email: "not-an-email" });

    await expect(page.getByRole("alert")).toHaveText("Enter a valid email address");
    await expect(page.getByRole("status")).toBeEmpty();

    // Re-read the stored state: the failed request did not refresh the count itself.
    await page.reload();
    await expect(page.getByText("0 subscribers")).toBeVisible();
  });

  test("an already subscribed address shows an error and is not counted twice", async ({ page }) => {
    const email = page.getByLabel("Email address");
    const subscribe = page.getByRole("button", { name: "Subscribe" });

    await email.fill("repeat@example.com");
    await subscribe.click();
    await expect(page.getByText("1 subscriber", { exact: true })).toBeVisible();

    await email.fill("repeat@example.com");
    await subscribe.click();
    await expect(page.getByRole("alert")).toHaveText("That email is already subscribed");
    await expect(page.getByRole("status")).toBeEmpty();

    await page.reload();
    await expect(page.getByText("1 subscriber", { exact: true })).toBeVisible();
  });

  test("pressing Enter in the email field subscribes like the button", async ({ page }) => {
    const call = page.waitForRequest(isSubscribePost);
    const email = page.getByLabel("Email address");
    await email.fill("enter@example.com");
    await email.press("Enter");
    expect((await call).postDataJSON()).toEqual({ email: "enter@example.com" });

    await expect(page.getByRole("status")).toHaveText("Thanks, you're subscribed");
    await expect(page.getByText("1 subscriber", { exact: true })).toBeVisible();
  });

  test("the email field is emptied after a successful subscription", async ({ page }) => {
    const email = page.getByLabel("Email address");
    await email.fill("cleared@example.com");
    await page.getByRole("button", { name: "Subscribe" }).click();

    await expect(page.getByRole("status")).toHaveText("Thanks, you're subscribed");
    await expect(email).toHaveValue("");
  });
});

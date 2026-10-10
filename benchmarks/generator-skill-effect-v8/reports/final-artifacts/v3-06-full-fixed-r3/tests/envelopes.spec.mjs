import { expect, test } from "@playwright/test";

const envelope = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name, exact: true }) });

test.beforeEach(async ({ page, request }) => {
  await request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Budget envelopes", exact: true })).toBeVisible();
});

test("shows the seeded envelope cards and total", async ({ page }) => {
  await expect(page.getByRole("article")).toHaveCount(3);

  await expect(envelope(page, "Groceries").getByText("$120 of $300")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Groceries spending", exact: true })).toHaveAttribute(
    "aria-valuenow",
    "40",
  );

  await expect(envelope(page, "Transport").getByText("$150 of $150")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Transport spending", exact: true })).toHaveAttribute(
    "aria-valuenow",
    "100",
  );

  await expect(envelope(page, "Fun").getByText("$0 of $100")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Fun spending", exact: true })).toHaveAttribute(
    "aria-valuenow",
    "0",
  );

  await expect(page.getByText("Total $270 of $550")).toBeVisible();
});

test("adds spending and keeps it after reload", async ({ page }) => {
  const groceries = envelope(page, "Groceries");
  const spendRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/envelopes/groceries/spend",
  );

  await page.getByRole("textbox", { name: "Add spending Groceries", exact: true }).fill("45");
  await page.getByRole("button", { name: "Add spending to Groceries", exact: true }).click();

  expect((await spendRequest).postDataJSON()).toEqual({ amount: 45 });
  await expect(groceries.getByText("$165 of $300")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Groceries spending", exact: true })).toHaveAttribute(
    "aria-valuenow",
    "55",
  );
  await expect(page.getByText("Total $315 of $550")).toBeVisible();

  await page.reload();
  await expect(groceries.getByText("$165 of $300")).toBeVisible();
  await expect(page.getByText("Total $315 of $550")).toBeVisible();
});

test("shows over budget only after spending exceeds the limit", async ({ page }) => {
  const transport = envelope(page, "Transport");
  await expect(transport.getByText("$150 of $150")).toBeVisible();
  await expect(transport.getByText("Over budget")).toBeHidden();

  const spendRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/envelopes/transport/spend",
  );

  await page.getByRole("textbox", { name: "Add spending Transport", exact: true }).fill("1");
  await page.getByRole("button", { name: "Add spending to Transport", exact: true }).click();

  expect((await spendRequest).postDataJSON()).toEqual({ amount: 1 });
  await expect(transport.getByText("$151 of $150")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Transport spending", exact: true })).toHaveAttribute(
    "aria-valuenow",
    "100",
  );
  await expect(transport.getByText("Over budget")).toBeVisible();
  await expect(page.getByText("Total $271 of $550")).toBeVisible();
});

test("resets an envelope to zero and removes its over budget badge", async ({ page }) => {
  const fun = envelope(page, "Fun");

  await page.getByRole("textbox", { name: "Add spending Fun", exact: true }).fill("125");
  await page.getByRole("button", { name: "Add spending to Fun", exact: true }).click();
  await expect(fun.getByText("$125 of $100")).toBeVisible();
  await expect(fun.getByText("Over budget")).toBeVisible();

  const resetRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/envelopes/fun/reset",
  );

  await page.getByRole("button", { name: "Reset Fun", exact: true }).click();

  expect((await resetRequest).postData()).toBeNull();
  await expect(fun.getByText("$0 of $100")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Fun spending", exact: true })).toHaveAttribute(
    "aria-valuenow",
    "0",
  );
  await expect(fun.getByText("Over budget")).toBeHidden();
  await expect(page.getByText("Total $270 of $550")).toBeVisible();
});

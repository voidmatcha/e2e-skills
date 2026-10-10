import { expect, test } from "@playwright/test";

const envelope = (page, name) =>
  page.getByRole("article").filter({ has: page.getByRole("heading", { name, exact: true }) });

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Budget envelopes", exact: true })).toBeVisible();
});

test("shows seeded envelopes with totals and progress", async ({ page }) => {
  await expect(page.getByRole("heading", { level: 2 })).toHaveText([
    "Groceries",
    "Transport",
    "Fun",
  ]);
  await expect(page.getByText("Total $270 of $550")).toBeVisible();

  await expect(envelope(page, "Groceries").getByText("$120 of $300")).toBeVisible();
  await expect(
    page.getByRole("progressbar", { name: "Groceries spending", exact: true }),
  ).toHaveAttribute(
    "aria-valuenow",
    "40",
  );

  await expect(envelope(page, "Transport").getByText("$150 of $150")).toBeVisible();
  await expect(
    page.getByRole("progressbar", { name: "Transport spending", exact: true }),
  ).toHaveAttribute(
    "aria-valuenow",
    "100",
  );
  await expect(envelope(page, "Transport").getByText("Over budget")).toBeHidden();

  await expect(envelope(page, "Fun").getByText("$0 of $100")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Fun spending", exact: true })).toHaveAttribute(
    "aria-valuenow",
    "0",
  );
});

test("adds spending and keeps it after reload", async ({ page }) => {
  await page.getByRole("textbox", { name: "Add spending Groceries", exact: true }).fill("80");
  const spendRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().endsWith("/api/envelopes/groceries/spend") &&
      request.postDataJSON().amount === 80,
  );
  const spendResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/envelopes/groceries/spend") &&
      response.ok(),
  );

  await page.getByRole("button", { name: "Add spending to Groceries", exact: true }).click();
  await spendRequest;
  await spendResponse;

  await expect(envelope(page, "Groceries").getByText("$200 of $300")).toBeVisible();
  await expect(
    page.getByRole("progressbar", { name: "Groceries spending", exact: true }),
  ).toHaveAttribute(
    "aria-valuenow",
    "67",
  );
  await expect(page.getByText("Total $350 of $550")).toBeVisible();

  await page.reload();
  await expect(envelope(page, "Groceries").getByText("$200 of $300")).toBeVisible();
  await expect(page.getByText("Total $350 of $550")).toBeVisible();
});

test("shows over budget only above the limit and clears it on reset", async ({ page }) => {
  await expect(envelope(page, "Transport").getByText("$150 of $150")).toBeVisible();
  await expect(envelope(page, "Transport").getByText("Over budget")).toBeHidden();

  await page.getByRole("textbox", { name: "Add spending Fun", exact: true }).fill("125");
  const spendRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().endsWith("/api/envelopes/fun/spend") &&
      request.postDataJSON().amount === 125,
  );
  const spendResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/envelopes/fun/spend") &&
      response.ok(),
  );

  await page.getByRole("button", { name: "Add spending to Fun", exact: true }).click();
  await spendRequest;
  await spendResponse;

  await expect(envelope(page, "Fun").getByText("$125 of $100")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Fun spending", exact: true })).toHaveAttribute(
    "aria-valuenow",
    "100",
  );
  await expect(envelope(page, "Fun").getByText("Over budget")).toBeVisible();
  await expect(page.getByText("Total $395 of $550")).toBeVisible();

  const resetRequest = page.waitForRequest(
    (request) =>
      request.method() === "POST" && request.url().endsWith("/api/envelopes/fun/reset"),
  );
  const resetResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/envelopes/fun/reset") &&
      response.ok(),
  );

  await page.getByRole("button", { name: "Reset Fun", exact: true }).click();
  await resetRequest;
  await resetResponse;

  await expect(envelope(page, "Fun").getByText("$0 of $100")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Fun spending", exact: true })).toHaveAttribute(
    "aria-valuenow",
    "0",
  );
  await expect(envelope(page, "Fun").getByText("Over budget")).toBeHidden();
  await expect(page.getByText("Total $270 of $550")).toBeVisible();
});

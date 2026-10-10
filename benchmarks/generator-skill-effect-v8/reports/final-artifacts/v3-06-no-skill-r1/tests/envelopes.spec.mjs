import { expect, test } from "@playwright/test";

const envelope = (page, name) =>
  page.locator("article").filter({ has: page.getByRole("heading", { name }) });

test.beforeEach(async ({ request }) => {
  await request.post("/api/reset");
});

test("shows the starting budget envelopes and total", async ({ page }) => {
  await page.goto("/");

  await expect(envelope(page, "Groceries")).toContainText("$120 of $300");
  await expect(envelope(page, "Transport")).toContainText("$150 of $150");
  await expect(envelope(page, "Fun")).toContainText("$0 of $100");
  await expect(page.getByText("Total $270 of $550")).toBeVisible();

  await expect(page.getByRole("progressbar", { name: "Groceries spending" })).toHaveAttribute("aria-valuenow", "40");
  await expect(page.getByRole("progressbar", { name: "Transport spending" })).toHaveAttribute("aria-valuenow", "100");
  await expect(page.getByRole("progressbar", { name: "Fun spending" })).toHaveAttribute("aria-valuenow", "0");

  await expect(envelope(page, "Groceries").getByText("Over budget")).toBeHidden();
  await expect(envelope(page, "Transport").getByText("Over budget")).toBeHidden();
  await expect(envelope(page, "Fun").getByText("Over budget")).toBeHidden();
});

test("adds spending, caps progress at 100 percent, and persists after reload", async ({ page }) => {
  await page.goto("/");

  await envelope(page, "Groceries").getByRole("textbox", { name: "Add spending Groceries" }).fill("210");
  await page.getByRole("button", { name: "Add spending to Groceries" }).click();

  await expect(envelope(page, "Groceries")).toContainText("$330 of $300");
  await expect(page.getByRole("progressbar", { name: "Groceries spending" })).toHaveAttribute("aria-valuenow", "100");
  await expect(envelope(page, "Groceries").getByText("Over budget")).toBeVisible();
  await expect(page.getByText("Total $480 of $550")).toBeVisible();

  await page.reload();

  await expect(envelope(page, "Groceries")).toContainText("$330 of $300");
  await expect(page.getByRole("progressbar", { name: "Groceries spending" })).toHaveAttribute("aria-valuenow", "100");
  await expect(envelope(page, "Groceries").getByText("Over budget")).toBeVisible();
  await expect(page.getByText("Total $480 of $550")).toBeVisible();
});

test("resets an envelope and removes the over budget badge", async ({ page }) => {
  await page.goto("/");

  await envelope(page, "Transport").getByRole("textbox", { name: "Add spending Transport" }).fill("1");
  await page.getByRole("button", { name: "Add spending to Transport" }).click();
  await expect(envelope(page, "Transport")).toContainText("$151 of $150");
  await expect(envelope(page, "Transport").getByText("Over budget")).toBeVisible();

  await page.getByRole("button", { name: "Reset Transport" }).click();

  await expect(envelope(page, "Transport")).toContainText("$0 of $150");
  await expect(page.getByRole("progressbar", { name: "Transport spending" })).toHaveAttribute("aria-valuenow", "0");
  await expect(envelope(page, "Transport").getByText("Over budget")).toBeHidden();
  await expect(page.getByText("Total $120 of $550")).toBeVisible();
});

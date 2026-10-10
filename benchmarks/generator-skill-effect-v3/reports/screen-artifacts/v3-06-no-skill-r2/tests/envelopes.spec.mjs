import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request }) => {
  const res = await request.post("/api/reset");
  expect(res.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page.getByText("Total $270 of $550")).toBeVisible();
});

const envelope = (page, name) => page.locator("article").filter({ has: page.getByRole("heading", { name }) });

async function addSpending(page, name, amount) {
  await page.getByRole("textbox", { name: `Add spending ${name}` }).fill(String(amount));
  await page.getByRole("button", { name: `Add spending to ${name}` }).click();
}

test("shows the seeded envelopes", async ({ page }) => {
  await expect(envelope(page, "Groceries").getByText("$120 of $300")).toBeVisible();
  await expect(envelope(page, "Transport").getByText("$150 of $150")).toBeVisible();
  await expect(envelope(page, "Fun").getByText("$0 of $100")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Groceries spending" })).toHaveAttribute("aria-valuenow", "40");
  await expect(page.getByRole("progressbar", { name: "Transport spending" })).toHaveAttribute("aria-valuenow", "100");
  await expect(page.getByRole("progressbar", { name: "Fun spending" })).toHaveAttribute("aria-valuenow", "0");
  await expect(page.getByText("Over budget").filter({ visible: true })).toHaveCount(0);
});

test("adding spending updates the amount, progress bar and total", async ({ page }) => {
  await addSpending(page, "Groceries", 30);
  await expect(envelope(page, "Groceries").getByText("$150 of $300")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Groceries spending" })).toHaveAttribute("aria-valuenow", "50");
  await expect(page.getByText("Total $300 of $550")).toBeVisible();
});

test("progress bar is capped at 100 when over the limit", async ({ page }) => {
  await addSpending(page, "Transport", 150);
  await expect(envelope(page, "Transport").getByText("$300 of $150")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Transport spending" })).toHaveAttribute("aria-valuenow", "100");
  await expect(page.getByText("Total $420 of $550")).toBeVisible();
});

test("Over budget badge appears only when spending exceeds the limit", async ({ page }) => {
  const fun = envelope(page, "Fun");
  await addSpending(page, "Fun", 100);
  await expect(fun.getByText("$100 of $100")).toBeVisible();
  await expect(fun.getByText("Over budget")).toBeHidden();

  await addSpending(page, "Fun", 1);
  await expect(fun.getByText("$101 of $100")).toBeVisible();
  await expect(fun.getByText("Over budget")).toBeVisible();
  await expect(envelope(page, "Groceries").getByText("Over budget")).toBeHidden();
});

test("an envelope at exactly its limit shows no badge", async ({ page }) => {
  await expect(envelope(page, "Transport").getByText("Over budget")).toBeHidden();
});

test("Reset envelope clears spending and the badge", async ({ page }) => {
  const transport = envelope(page, "Transport");
  await addSpending(page, "Transport", 10);
  await expect(transport.getByText("Over budget")).toBeVisible();

  await page.getByRole("button", { name: "Reset Transport" }).click();
  await expect(transport.getByText("$0 of $150")).toBeVisible();
  await expect(transport.getByText("Over budget")).toBeHidden();
  await expect(page.getByRole("progressbar", { name: "Transport spending" })).toHaveAttribute("aria-valuenow", "0");
  await expect(page.getByText("Total $120 of $550")).toBeVisible();
});

test("spending survives a reload", async ({ page }) => {
  await addSpending(page, "Fun", 25);
  await expect(envelope(page, "Fun").getByText("$25 of $100")).toBeVisible();

  await page.reload();
  await expect(envelope(page, "Fun").getByText("$25 of $100")).toBeVisible();
  await expect(page.getByText("Total $295 of $550")).toBeVisible();
});

test("a reset also survives a reload", async ({ page }) => {
  await page.getByRole("button", { name: "Reset Groceries" }).click();
  await expect(envelope(page, "Groceries").getByText("$0 of $300")).toBeVisible();

  await page.reload();
  await expect(envelope(page, "Groceries").getByText("$0 of $300")).toBeVisible();
  await expect(page.getByText("Total $150 of $550")).toBeVisible();
});

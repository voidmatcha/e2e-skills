import { expect, test } from "@playwright/test";

const entries = (page) => page.getByRole("list", { name: "Entries" }).getByRole("listitem");

async function sign(page, name, message) {
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Message").fill(message);
  await page.getByRole("button", { name: "Sign" }).click();
}

test.beforeEach(async ({ page }) => {
  await page.request.post("/api/reset");
  await page.goto("/");
});

test("adds an entry showing name and message", async ({ page }) => {
  await sign(page, "Ada", "Hello there");
  await expect(entries(page)).toHaveCount(1);
  await expect(entries(page).first()).toContainText("Ada");
  await expect(entries(page).first()).toContainText("Hello there");
});

test("lists newest first", async ({ page }) => {
  await sign(page, "Ada", "First note");
  await sign(page, "Grace", "Second note");
  await expect(entries(page)).toHaveText([/Second note/, /First note/]);
});

test("counts entries", async ({ page }) => {
  await expect(page.getByText("0 entries")).toBeVisible();
  await sign(page, "Ada", "One");
  await expect(page.getByText("1 entry", { exact: true })).toBeVisible();
  await sign(page, "Grace", "Two");
  await expect(page.getByText("2 entries")).toBeVisible();
});

test("stores entries on the server", async ({ page }) => {
  await sign(page, "Ada", "Kept");
  await expect(entries(page)).toHaveCount(1);
  await page.reload();
  await expect(entries(page)).toHaveCount(1);
  await expect(entries(page).first()).toContainText("Kept");
});

test("rejects an empty message", async ({ page }) => {
  await sign(page, "Ada", "");
  await expect(page.getByRole("alert")).toHaveText("Message is required");
  await expect(entries(page)).toHaveCount(0);
  await page.reload();
  await expect(entries(page)).toHaveCount(0);
});

test("clears the error after a later successful submission", async ({ page }) => {
  await sign(page, "Ada", "");
  await expect(page.getByRole("alert")).toHaveText("Message is required");
  await sign(page, "Ada", "Fixed");
  await expect(entries(page)).toHaveCount(1);
  await expect(page.getByRole("alert")).toHaveText("");
});

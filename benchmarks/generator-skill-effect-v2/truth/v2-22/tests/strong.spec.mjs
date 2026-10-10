import { expect, test } from "@playwright/test";

const rows = (page) => page.getByRole("list", { name: "Orders" }).getByRole("listitem");

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(rows(page)).toHaveCount(8);
  await expect(page.getByText("8 orders")).toBeVisible();
});

test("status and search combine with AND and the count follows", async ({ page }) => {
  await page.getByLabel("Status").selectOption("shipped");
  await expect(rows(page)).toHaveText([/#1002/, /#1010/, /#1020/]);
  await expect(page.getByText("3 orders")).toBeVisible();
  await page.getByLabel("Search").fill("10");
  await expect(rows(page)).toHaveText([/#1002/, /#1010/, /#1020/]);
  await expect(page.getByText("3 orders")).toBeVisible();
  await page.getByLabel("Search").fill("101");
  await expect(rows(page)).toHaveText([/#1010/]);
  await expect(page.getByText("1 order", { exact: true })).toBeVisible();
  await page.getByLabel("Search").fill("20");
  await expect(rows(page)).toHaveText([/#1020/]);
});

test("filters are mirrored in the URL and restored from it", async ({ page }) => {
  await page.getByLabel("Status").selectOption("shipped");
  await page.getByLabel("Search").fill("101");
  await expect(page).toHaveURL(/\?status=shipped&q=101$/);
  await page.reload();
  await expect(rows(page)).toHaveText([/#1010/]);
  await expect(page.getByLabel("Status")).toHaveValue("shipped");
  await expect(page.getByLabel("Search")).toHaveValue("101");
  await page.goto("/?status=refunded");
  await expect(rows(page)).toHaveText([/#1003/, /#2010/]);
  await expect(page.getByLabel("Status")).toHaveValue("refunded");
  await expect(page.getByText("2 orders")).toBeVisible();
});

test("clear filters empties both controls", async ({ page }) => {
  await page.getByLabel("Status").selectOption("paid");
  await page.getByLabel("Search").fill("200");
  await expect(rows(page)).toHaveText([/#2001/]);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByLabel("Status")).toHaveValue("");
  await expect(page.getByLabel("Search")).toHaveValue("");
  await expect(rows(page)).toHaveCount(8);
  await expect(page).toHaveURL(/\/$/);
});

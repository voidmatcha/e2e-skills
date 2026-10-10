import { expect, test } from "@playwright/test";

test("opens exactly the chosen title once and persists it", async ({ page }) => {
  await page.goto("/");
  const north = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Open North" }) });
  const south = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Open South" }) });
  await expect(page.getByRole("status")).toHaveText("Unread: 2");

  await page.getByRole("button", { name: "Open North" }).click();
  await expect(page.getByRole("status")).toHaveText("Unread: 1");
  await expect(north).toContainText("North: Read · 1 open");
  await expect(south).toContainText("South: Unread · 0 opens");

  await page.getByRole("button", { name: "Open South" }).click();
  await expect(page.getByRole("status")).toHaveText("Unread: 0");
  await expect(south).toContainText("South: Read · 1 open");

  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Unread: 0");
  await expect(north).toContainText("North: Read · 1 open");
  await expect(south).toContainText("South: Read · 1 open");

  await page.getByRole("button", { name: "Open North" }).click();
  await expect(page.getByRole("status")).toHaveText("Unread: 0");
  await expect(north).toContainText("North: Read · 2 opens");
  await expect(south).toContainText("South: Read · 1 open");
});

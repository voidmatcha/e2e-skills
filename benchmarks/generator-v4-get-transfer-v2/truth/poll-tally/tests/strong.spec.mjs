import { expect, test } from "@playwright/test";

test("counts only the chosen vote once and persists it", async ({ page }) => {
  await page.goto("/");
  const ruby = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Vote Ruby" }) });
  const blue = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Vote Blue" }) });
  await expect(page.getByRole("status")).toHaveText("Total votes: 0");

  await page.getByRole("button", { name: "Vote Ruby" }).click();
  await expect(page.getByRole("status")).toHaveText("Total votes: 1");
  await expect(ruby).toContainText("Ruby: 1 votes");
  await expect(blue).toContainText("Blue: 0 votes");

  await page.getByRole("button", { name: "Vote Blue" }).click();
  await expect(page.getByRole("status")).toHaveText("Total votes: 2");
  await expect(ruby).toContainText("Ruby: 1 votes");
  await expect(blue).toContainText("Blue: 1 votes");

  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Total votes: 2");
  await expect(ruby).toContainText("Ruby: 1 votes");
  await expect(blue).toContainText("Blue: 1 votes");

  await page.getByRole("button", { name: "Vote Ruby" }).click();
  await expect(page.getByRole("status")).toHaveText("Total votes: 3");
  await expect(ruby).toContainText("Ruby: 2 votes");
  await expect(blue).toContainText("Blue: 1 votes");
});

import { expect, test } from "@playwright/test";

test("proves the increment request fired", async ({ page }) => {
  const query =
    process.env.FIXTURE_FAULT_MODE === "write" ? "?write-fault" : "";
  await page.goto(`/${query}`);

  const request = page.waitForRequest(
    (candidate) =>
      candidate.url().endsWith("/api/increment") &&
      candidate.method() === "POST",
    { timeout: 5000 },
  );
  await page.getByRole("button", { name: "Increment" }).click();
  await request;
  await expect(page.getByRole("status")).toHaveText("Count: 1");
});

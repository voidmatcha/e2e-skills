import { expect, test } from "@playwright/test";

const DOM_CHANGE_DELAY_MS = 500;

async function installDelayedStatus(page) {
  page.on("console", (message) => console.log(message.text()));
  await page.setContent(`
    <main>
      <p id="status">waiting</p>
    </main>
    <script>
      setTimeout(() => {
        document.querySelector("#status").textContent = "ready";
        console.log("PROBE_DOM_CHANGE_APPLIED");
      }, ${DOM_CHANGE_DELAY_MS});
    </script>
  `);
}

test("#4g finite short timeout fails before delayed DOM change", async ({
  page,
}) => {
  test.setTimeout(2500);
  await installDelayedStatus(page);
  console.log("PROBE_FINITE_SHORT_STARTED");

  await expect(page.locator("#status")).toHaveText("ready", { timeout: 100 });
});

test("#4g timeout zero retries until delayed DOM change", async ({ page }) => {
  test.setTimeout(2500);
  await installDelayedStatus(page);
  console.log("PROBE_TIMEOUT_ZERO_STARTED");
  const startedAt = Date.now();

  await expect(page.locator("#status")).toHaveText("ready", { timeout: 0 });

  const elapsedMs = Date.now() - startedAt;
  expect(elapsedMs).toBeGreaterThanOrEqual(350);
  expect(elapsedMs).toBeLessThan(2000);
  console.log(`PROBE_TIMEOUT_ZERO_PASSED elapsed_ms=${elapsedMs}`);
});

test("#4g timeout zero missing target is bounded by test timeout", async ({
  page,
}) => {
  test.setTimeout(1200);
  await page.setContent('<main><p id="status">waiting</p></main>');
  console.log("PROBE_TIMEOUT_ZERO_CONTROL_STARTED");

  await expect(page.locator("#status")).toHaveText("never", { timeout: 0 });
});

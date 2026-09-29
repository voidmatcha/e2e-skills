import { test, expect } from '@playwright/test';

function permitsLeft(text: string | null): number {
  return Math.max(0, Number.parseInt(text ?? '0', 10) || 0);
}

test('renders the zone B permit counter', async ({ page }) => {
  await page.goto('/permits/zones/b');
  const counter = page.getByTestId('zone-b-remaining');
  await expect(counter).toBeVisible();
  expect(permitsLeft(await counter.textContent())).toBeGreaterThanOrEqual(0);
});

test('issuing a permit lowers the zone B counter', async ({ page }) => {
  await page.goto('/permits/zones/b');
  const counter = page.getByTestId('zone-b-remaining');
  await expect(counter).toHaveText('12');
  await page.getByRole('button', { name: 'Issue permit', exact: true }).click();
  await expect.poll(async () => permitsLeft(await counter.textContent())).toBeLessThan(12);
});

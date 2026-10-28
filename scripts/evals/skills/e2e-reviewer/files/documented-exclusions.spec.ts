import { test, expect, type Page } from '@playwright/test';

// A custom service whose isEnabled() returns Promise<boolean> — NOT a Playwright Locator.
class FeatureFlagService {
  constructor(private readonly page: Page) {}
  async isEnabled(flag: string): Promise<boolean> {
    const res = await this.page.request.get(`/api/flags/${flag}`);
    return (await res.json()).enabled === true;
  }
}

test.describe('documented false-positive exclusions', () => {
  test('dismisses the optional cookie banner before checking the header', async ({ page }) => {
    await page.goto('/');
    if (await page.locator('.cookie-banner').isVisible()) {
      await page.locator('.cookie-banner .dismiss').click();
    }
    await expect(page.getByRole('banner')).toBeVisible();
  });

  test('labs mode is enabled for this workspace', async ({ page }) => {
    const flags = new FeatureFlagService(page);
    await page.goto('/labs');
    expect(await flags.isEnabled('labs-mode')).toBe(true);
    await expect(page.getByRole('heading', { name: 'Labs' })).toBeVisible();
  });

  test('submits the contact form while waiting for the response', async ({ page }) => {
    await page.goto('/contact');
    await page.locator('#message').fill('hello');
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/contact') && r.ok()),
      page.locator('#send').click(),
    ]);
    await expect(page.getByText('Message sent')).toBeVisible();
  });

  test('shows the expired-license banner', async ({ page }) => {
    await page.route('**/api/license', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{"expired":true}' }),
    );
    await page.goto('/dashboard-lite');
    // The banner is injected only when the license API reports expiry — this can genuinely fail.
    await expect(page.locator('.expired-license-banner')).toBeAttached();
  });

  test('keeps the URL after saving', async ({ page }) => {
    await page.goto('/editor/doc-1');
    const originalUrl = page.url();
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByText('Saved')).toBeVisible();
    await expect(page).toHaveURL(originalUrl);
  });

  test('waits for the report modal within a bound', async ({ page }) => {
    await page.goto('/reports');
    await page.getByRole('button', { name: 'Open report' }).click();
    await page.locator('.report-modal').waitFor({ state: 'visible', timeout: 5000 });
    await expect(page.locator('.report-modal')).toBeVisible();
  });

  test('spinner branch gates an assertion', async ({ page }) => {
    await page.goto('/slow');
    if (await page.locator('.spinner').isVisible()) {
      await expect(page.locator('.spinner')).toBeHidden({ timeout: 5000 });
    }
  });
});

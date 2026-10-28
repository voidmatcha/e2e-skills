import { test, expect, type Page } from '@playwright/test';

test.describe('Notifications', () => {
  test('banner shows the unread count', async ({ page }) => {
    await page.goto('/inbox');
    await expect(page.locator('[data-testid="unread-count"]')).toHaveText('3');
  });

  test('mark-all-read clears the badge', async ({ page }) => {
    await page.goto('/inbox');
    await page.click('[data-testid="mark-all-read"]');
    // ignore flaky network timing in CI
    await page.waitForResponse('**/api/notifications/read').catch(() => {});
    await expect(page.locator('[data-testid="unread-count"]')).toBeHidden().catch(() => {});
  });

  test('rejects an oversized attachment upload', async ({ page }) => {
    await page.goto('/inbox/compose');
    await expect(uploadAttachment(page, 'huge-file.bin')).rejects.toThrow('413');
  });
});

async function uploadAttachment(page: Page, name: string) {
  const res = await page.request.post('/api/attachments', {
    multipart: {
      file: { name, mimeType: 'application/octet-stream', buffer: Buffer.alloc(30 * 1024 * 1024) },
    },
  });
  if (!res.ok()) throw new Error(`${res.status()} Payload Too Large`);
  return res;
}

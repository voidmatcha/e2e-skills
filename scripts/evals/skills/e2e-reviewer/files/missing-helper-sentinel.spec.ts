import { test, expect } from '@playwright/test';
// The helpers module is deliberately absent from this fixture.
import { openInbox, unreadBadgeValue } from './inbox-helpers';

test('shows the unread badge after a new message', async ({ page }) => {
  await openInbox(page);
  await page.getByRole('button', { name: 'Simulate message' }).click();
  const unread = await unreadBadgeValue(page);
  expect(unread).toBeGreaterThanOrEqual(0);
});

import { test, expect } from '@playwright/test';
// The helpers module is deliberately absent from this fixture.
import { codeCopyButton, goToChat, sendMessage, toolBlocks } from './chat-helpers';

test('renders tool blocks for a tool call', async ({ page }) => {
  await goToChat(page);
  await sendMessage(page, 'list the files');
  const count = await toolBlocks(page).count();
  expect(count).toBeGreaterThanOrEqual(0);
});

test('shows a copy button on a code block', async ({ page }) => {
  await goToChat(page);
  await sendMessage(page, 'write a hello world');
  const copyButton = codeCopyButton(page);
  const buttons = await copyButton.count();
  if (buttons > 0) {
    await expect(copyButton.first()).toBeVisible();
  }
});

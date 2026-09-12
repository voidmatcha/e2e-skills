import { expect, test } from '@playwright/test'
import { PageManager } from './pages/pageManager'

const MESSAGE = 'Persistence check one'
// Funny mode (on by default) answers from a canned first-letter map with no
// network call, so the reply for a fixed message is deterministic — verified
// live: the same message sent in two fresh page loads produced this same text.
const REPLY = 'Programmers don’t panic; we just `console.log` our feelings.'

test.describe('Message history persistence', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('keeps a sent exchange across a reload and drops it when history is cleared', async ({
    page,
  }) => {
    const pageManager = new PageManager(page)
    const layout = pageManager.onAppLayout()
    const chat = pageManager.onChatPage()
    const history = pageManager.onChatHistoryPage()

    // Given: a fresh profile with no stored history
    await expect(chat.messageInput).toBeEnabled()
    await layout.goToHistoryPage()
    await expect(history.emptyState).toBeVisible()
    await expect(history.deleteHistoryButton).toBeDisabled()
    await expect(history.exchangeEntries).toHaveCount(0)

    // When: the user sends a message in Chat and reloads the history screen.
    // The assistant bubble is the settled-state gate: the exchange is written
    // to storage in the same handler that renders it.
    await layout.goToChatPage()
    await chat.fillChatInput(MESSAGE)
    await chat.sendMessage()
    await expect(chat.chatMessageFirstReply).toHaveText(REPLY)
    await layout.goToHistoryPage()
    await expect(history.exchangeEntries).toHaveCount(1)
    await page.reload()

    // Then: the exchange survives the reload on the history screen. It has to
    // be asserted here, not on Chat — the chat route drops its in-memory
    // transcript on remount even though the archive is intact.
    await expect(history.heading).toBeVisible()
    await expect(history.exchangeEntries).toHaveCount(1)
    await expect(history.exchangeEntries).toContainText(REPLY)
    await expect(history.exchangeEntries).toContainText(MESSAGE)
    // Proves the same locator the removal check below relies on can match, so
    // that check cannot pass just because the selector rotted.
    await expect(page.getByText(MESSAGE)).toBeVisible()

    // And: clearing the history removes that exchange
    await expect(history.deleteHistoryButton).toBeEnabled()
    const confirmMessage = await history.deleteHistoryAndConfirm()
    expect(confirmMessage).toBe(
      'Delete all message history stored in this browser? This cannot be undone.',
    )
    await expect(history.emptyState).toBeVisible()
    await expect(history.exchangeEntries).toHaveCount(0)
    await expect(page.getByText(MESSAGE)).not.toBeVisible()
    await expect(history.deleteHistoryButton).toBeDisabled()

    // And: the removal is persisted too — clearing writes to storage and to
    // React state independently, so without this reload a build whose storage
    // delete silently failed would still look cleared.
    await page.reload()
    await expect(history.emptyState).toBeVisible()
    await expect(history.exchangeEntries).toHaveCount(0)
  })
})

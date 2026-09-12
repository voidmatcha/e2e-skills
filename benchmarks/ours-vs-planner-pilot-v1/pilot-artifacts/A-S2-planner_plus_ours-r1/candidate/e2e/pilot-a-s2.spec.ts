import { expect, test } from '@playwright/test'
import { PageManager } from './pages/pageManager'

const MESSAGE = 'Hello there!'
// Funny mode is on by default and its replies are a pure lookup
// (src/lib/funnyReply.ts) — this exact pair is deterministic, and
// e2e/tests/chat.spec.ts already relies on it.
const REPLY = 'GENERAL KENOBI!!'

test.describe('Message history persistence', () => {
  test('keeps a sent exchange across a reload and drops it when history is cleared', async ({
    page,
  }) => {
    const pageManager = new PageManager(page)
    const chat = pageManager.onChatPage()
    const layout = pageManager.onAppLayout()
    const history = pageManager.onChatHistoryPage()

    // Given: a fresh context (empty localStorage) on the chat screen. The
    // composer stays disabled until the app has finished its initial history
    // load, so waiting for it is the app's own ready signal.
    await page.goto('/')
    await expect(chat.messageInput).toBeEnabled()
    expect(await history.readRawStoredHistory()).toBeNull()

    // When: the user sends a message and gets a reply
    await chat.fillChatInput(MESSAGE)
    await expect(chat.sendButton).toBeEnabled()
    await chat.sendMessage()
    await expect(chat.chatMessageFirst).toHaveText(MESSAGE)
    await expect(chat.chatMessageFirstReply).toHaveText(REPLY)

    // ...and then reloads the page. The chat thread itself is in-memory and
    // resets on reload by design; the archive is what must survive.
    await page.reload()
    await expect(chat.messageInput).toBeEnabled()
    await layout.goToHistoryPage()
    await expect(page).toHaveURL(/\/history$/)

    // Then: the message history screen still lists that exchange.
    const entry = history.entries.filter({ hasText: MESSAGE })
    await expect(entry).toHaveCount(1)
    await expect(entry).toContainText(REPLY)

    // ...and it survived because it reached the app's persistence boundary,
    // exactly once, with both halves of the exchange intact.
    const stored = await history.readStoredExchanges()
    expect(stored).toHaveLength(1)
    expect(stored[0]).toMatchObject({
      userContent: MESSAGE,
      assistantContent: REPLY,
    })

    // When: the user clears the history (and confirms the prompt)
    await history.clearHistory()

    // Then: the exchange is gone from the screen and from storage.
    await expect(entry).toHaveCount(0)
    await expect(history.emptyState).toBeVisible()
    await expect(history.deleteHistoryButton).toBeDisabled()
    await expect
      .poll(async () => await history.readRawStoredHistory())
      .toBeNull()
  })
})

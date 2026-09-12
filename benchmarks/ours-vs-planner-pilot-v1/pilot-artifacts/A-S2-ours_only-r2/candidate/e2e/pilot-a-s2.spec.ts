import { expect, test } from '@playwright/test'
import { ChatHistoryPage } from './pages/chatHistoryPage'
import { PageManager } from './pages/pageManager'

// Funny mode is on by default and answers this exact text with this exact
// canned line, offline (src/lib/funnyReply.ts) — so the exchange under test
// is deterministic without any backend.
const MESSAGE = 'Hello there!'
const REPLY = 'GENERAL KENOBI!!'

// The confirm the Delete history button is gated behind (HistoryPage.tsx).
const CONFIRM_TEXT =
  'Delete all message history stored in this browser? This cannot be undone.'

test.describe('Message history persistence', () => {
  test('a sent exchange survives a reload, and clearing history removes it', async ({
    page,
  }) => {
    const pageManager = new PageManager(page)
    const layout = pageManager.onAppLayout()
    const chat = pageManager.onChatPage()
    const history = new ChatHistoryPage(page)

    // Given: a fresh context on the chat screen — the composer stays disabled
    // until the app has finished looking for earlier messages.
    await page.goto('/')
    await expect(chat.messageInput).toBeEnabled({ timeout: 15_000 })

    // Given: an archive that starts out empty, so nothing below can pass on
    // state left over from an earlier run.
    await layout.goToHistoryPage()
    await expect(history.emptyState).toBeVisible()
    await expect(history.entries).toHaveCount(0)
    await expect(history.deleteHistoryButton).toBeDisabled()

    // When: the user sends a message and the assistant answers.
    await layout.goToChatPage()
    await expect(chat.messageInput).toBeEnabled({ timeout: 15_000 })
    await chat.fillChatInput(MESSAGE)
    await chat.sendMessage()
    await expect(chat.chatMessageFirstReply).toHaveText(REPLY)

    // The exchange is written to the app's only persistence boundary. The
    // chat thread itself is per-mount state, so without this write there
    // would be nothing for the reload below to find.
    expect(await history.readStoredExchanges()).toMatchObject([
      { userContent: MESSAGE, assistantContent: REPLY },
    ])

    // When: the user opens the history screen and reloads the page.
    await layout.goToHistoryPage()
    await expect(page).toHaveURL(/\/history$/)
    await expect(history.entries).toHaveCount(1)
    await page.reload()

    // Then: the history screen still lists that exchange.
    await expect(history.exchangeTexts).toHaveText([MESSAGE, REPLY])
    await expect(history.entries).toHaveCount(1)
    await expect(history.deleteHistoryButton).toBeEnabled()

    // When: the user clears the archive and confirms the prompt.
    expect(await history.clearHistoryAndConfirm()).toBe(CONFIRM_TEXT)

    // Then: the exchange is gone from the screen and from storage, and stays
    // gone across another reload.
    await expect(history.entries).toHaveCount(0)
    await expect(history.emptyState).toBeVisible()
    expect(await history.readStoredExchanges()).toBeNull()
    await page.reload()
    await expect(history.emptyState).toBeVisible()
    await expect(history.entries).toHaveCount(0)
  })
})

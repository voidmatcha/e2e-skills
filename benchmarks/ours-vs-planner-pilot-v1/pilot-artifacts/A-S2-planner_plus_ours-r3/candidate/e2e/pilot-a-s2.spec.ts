import { expect, test } from '@playwright/test'
import { ChatHistoryPage } from './pages/chatHistoryPage'
import { PageManager } from './pages/pageManager'

const MESSAGE = 'Persistence probe alpha'
// Funny mode is the default, and its reply is a pure function of the message's
// first letter ('P'), so this is deterministic rather than a captured sample.
const REPLY = 'Programmers don’t panic; we just `console.log` our feelings.'
const HISTORY_STORAGE_KEY = 'ai-assistant-chat-history-v1'

test.describe('Chat history persistence', () => {
  test('keeps a sent exchange in Message history across a reload, and clearing removes it', async ({
    page,
  }) => {
    const pageManager = new PageManager(page)
    const chat = pageManager.onChatPage()
    const layout = pageManager.onAppLayout()
    const chatHistory = new ChatHistoryPage(page)
    const exchangeRow = chatHistory.exchangeRows.filter({ hasText: MESSAGE })

    // Given: a fresh profile with empty client-side storage — the archive is
    // empty before anything is sent, so a row found later can only come from
    // this test's own message.
    await page.goto('/')
    // The composer stays disabled until the app finishes booting, so every
    // interaction is gated on it being enabled rather than merely present.
    await expect(chat.messageInput).toBeEnabled({ timeout: 15_000 })
    await layout.goToHistoryPage()
    await expect(chatHistory.heading).toBeVisible()
    await expect(chatHistory.emptyState).toBeVisible()
    await expect(chatHistory.exchangeRows).toHaveCount(0)
    await expect(chatHistory.deleteHistoryButton).toBeDisabled()

    // When: the user sends a message on the chat screen
    await layout.goToChatPage()
    await expect(chat.messageInput).toBeEnabled({ timeout: 15_000 })
    await chat.fillChatInput(MESSAGE)
    await expect(chat.sendButton).toBeEnabled()
    await chat.sendMessage()
    // The exchange is written to storage as the reply renders, so waiting for
    // the reply is what makes the reload below safe instead of a race.
    await expect(chat.chatMessageFirstReply).toHaveText(REPLY)

    // When: the page is reloaded
    await page.reload()
    await expect(chat.messageInput).toBeEnabled({ timeout: 15_000 })

    // Then: the message history screen still lists that exchange
    await layout.goToHistoryPage()
    await expect(chatHistory.heading).toBeVisible()
    await expect(exchangeRow).toHaveCount(1)
    await expect(exchangeRow).toContainText(REPLY)
    await expect(chatHistory.deleteHistoryButton).toBeEnabled()

    // Then: the exchange really is persisted client-side. This app has no
    // backend write to observe — persistence is localStorage — so the write is
    // proven at that seam, not just by the rendered list.
    // JUSTIFIED: evaluate() — localStorage is not reachable through a
    // Playwright locator API, and the rendered list alone cannot distinguish
    // stored state from in-memory state.
    await expect
      .poll(() => page.evaluate((key) => localStorage.getItem(key), HISTORY_STORAGE_KEY))
      .toContain(MESSAGE)

    // And: clearing history removes it. Deleting goes through a native
    // confirm(), which must be handled before the click or the clear never runs.
    page.once('dialog', (dialog) => dialog.accept())
    await chatHistory.deleteHistoryButton.click()
    await expect(exchangeRow).toHaveCount(0)
    await expect(chatHistory.emptyState).toBeVisible()
    // The button is driven by the stored exchange count, so it returning to
    // disabled shows the archive was emptied rather than merely re-rendered.
    await expect(chatHistory.deleteHistoryButton).toBeDisabled()

    // JUSTIFIED: evaluate() — same localStorage seam; proves the clear reached
    // storage instead of only updating the screen.
    await expect
      .poll(() => page.evaluate((key) => localStorage.getItem(key), HISTORY_STORAGE_KEY))
      .toBeNull()
  })
})

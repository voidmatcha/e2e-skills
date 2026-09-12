import { expect, test, type Page } from '@playwright/test'
import { PageManager } from './pages/pageManager'

const MESSAGE = 'Persistence check alpha'
const REPLY = 'Programmers don’t panic; we just `console.log` our feelings.'
const CONFIRM_MESSAGE =
  'Delete all message history stored in this browser? This cannot be undone.'
const STORAGE_KEY = 'ai-assistant-chat-history-v1'

/**
 * Reads the exchanges the app has persisted, or null when it has stored
 * nothing at all. localStorage is this app's only persistence seam (see
 * src/lib/chatHistoryStorage.ts), so the write itself can't be proven through
 * the page — the on-screen assertions below still carry the user-visible half
 * of the same behaviour.
 */
async function readStoredExchanges(page: Page) {
  // JUSTIFIED: the only alternative, context.storageState(), snapshots every
  // origin's storage and would still need this same key lookup; this reads
  // the app's documented storage key only, not arbitrary DOM.
  return page.evaluate((key) => {
    const raw = localStorage.getItem(key)
    if (raw === null) return null
    const stored = JSON.parse(raw) as {
      userContent: string
      assistantContent: string
    }[]
    return stored.map((exchange) => ({
      user: exchange.userContent,
      assistant: exchange.assistantContent,
    }))
  }, STORAGE_KEY)
}

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test.describe('Message history persistence', () => {
  test('keeps a sent exchange across a reload and drops it when history is cleared', async ({
    page,
  }) => {
    const pageManager = new PageManager(page)
    const chat = pageManager.onChatPage()
    const history = pageManager.onChatHistoryPage()
    const persistedExchange = history.exchangeItems
      .filter({ hasText: MESSAGE })
      .filter({ hasText: REPLY })

    // Given: a fresh profile with nothing stored yet. The composer stays
    // disabled until the app's initial message load settles, so waiting on it
    // is the app's own readiness signal rather than a timeout.
    await expect(chat.messageInput).toBeEnabled()
    await expect.poll(() => readStoredExchanges(page)).toBeNull()

    // When: the user sends a message and the assistant answers
    await chat.fillChatInput(MESSAGE)
    await chat.sendMessage()
    await expect(chat.chatMessageFirst).toHaveText(MESSAGE)
    await expect(chat.chatMessageFirstReply).toHaveText(REPLY)

    // Then: exactly one exchange reached the persistence seam. The reply
    // bubble above would look identical if the save had been dropped, and the
    // reload below is what the user actually depends on.
    await expect
      .poll(() => readStoredExchanges(page))
      .toEqual([{ user: MESSAGE, assistant: REPLY }])

    // When: the page is reloaded and the user opens Message history
    await page.reload()
    await pageManager.onAppLayout().goToHistoryPage()
    await expect(page).toHaveURL(/\/history$/)
    await expect(history.heading).toBeVisible()
    // Settled state: the toolbar button is only enabled once stored exchanges
    // exist and have been rendered.
    await expect(history.deleteHistoryButton).toBeEnabled()

    // Then: the exchange survived the reload and is listed exactly once
    await expect(persistedExchange).toHaveCount(1)

    // When: the user clears the history and confirms
    // The click can't be awaited first: window.confirm blocks inside the
    // button's own handler, so the dialog has to be settled before the click
    // promise can resolve.
    const dialogPromise = page.waitForEvent('dialog')
    const clearClick = history.deleteHistoryButton.click()
    const dialog = await dialogPromise
    expect(dialog.message()).toBe(CONFIRM_MESSAGE)
    await dialog.accept()
    await clearClick

    // Then: the exchange is gone from the screen and from storage
    await expect(persistedExchange).toHaveCount(0)
    await expect(history.emptyState).toBeVisible()
    await expect(history.deleteHistoryButton).toBeDisabled()
    await expect.poll(() => readStoredExchanges(page)).toBeNull()
  })
})

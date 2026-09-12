import { expect, test } from '@playwright/test'
import { PageManager } from './pages/pageManager'

const MESSAGE = 'Persistence probe alpha'
// Funny mode (on by default) answers from the first letter of the message, so
// a message starting with "P" always gets this reply. Asserted as a fragment
// to keep the typographic apostrophe in "don't" out of the spec.
const REPLY_FRAGMENT = 'we just `console.log` our feelings.'

test.describe('Message history persistence', () => {
  test('keeps a sent exchange across a reload and drops it when history is cleared', async ({
    page,
  }) => {
    const pageManager = new PageManager(page)
    const chat = pageManager.onChatPage()
    const layout = pageManager.onAppLayout()
    const history = pageManager.onChatHistoryPage()

    // Given: a fresh profile on the chat screen with nothing stored yet
    await page.goto('/')
    await expect(chat.messageInput).toBeEnabled({ timeout: 15_000 })
    expect(await history.readStoredExchanges()).toBeNull()

    // When: the user sends a message and the assistant answers
    await chat.fillChatInput(MESSAGE)
    await chat.sendMessage()
    await expect(chat.chatMessageFirst).toHaveText(MESSAGE)
    await expect(chat.chatMessageFirstReply).toContainText(REPLY_FRAGMENT)

    // The on-screen thread is only React state, so prove the exchange actually
    // reached the localStorage boundary before trusting the reload below.
    await expect
      .poll(async () => await history.readStoredExchanges())
      .toMatchObject([
        { userContent: MESSAGE, assistantContent: expect.stringContaining(REPLY_FRAGMENT) },
      ])

    // ...and reloads the page, which resets the on-screen thread
    await page.reload()
    await expect(chat.messageInput).toBeEnabled({ timeout: 15_000 })
    await layout.goToHistoryPage()

    // Then: the message history screen still lists that exchange
    await expect(page).toHaveURL(/\/history$/)
    await expect(history.heading).toBeVisible()
    await expect(history.exchangeItems).toContainText(MESSAGE)
    await expect(history.exchangeItems).toContainText(REPLY_FRAGMENT)
    await expect(history.exchangeItems).toHaveCount(1)

    // When: the user clears the stored history
    await history.deleteHistoryAndConfirm()

    // Then: the exchange is gone from the screen and from storage
    await expect(history.exchangeItems).toHaveCount(0)
    await expect(history.emptyState).toBeVisible()
    await expect(history.deleteHistoryButton).toBeDisabled()
    await expect.poll(async () => await history.readStoredExchanges()).toBeNull()
  })
})

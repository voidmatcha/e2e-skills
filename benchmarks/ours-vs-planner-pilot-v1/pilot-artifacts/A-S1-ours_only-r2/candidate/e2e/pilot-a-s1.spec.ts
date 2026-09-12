import { expect, test } from '@playwright/test'
import { PageManager } from './pages/pageManager'

/**
 * "Offline mode" here is the app's default standing state: Funny mode is on
 * and no chat backend is reachable, so the reply is produced entirely in the
 * browser from the first letter of the message. Observed live at
 * http://localhost:5174/: sending a message issues no POST /api/chat at all.
 *
 * "Keyboard shortcuts are neat" is deliberately a plain statement (no "?")
 * and is not the "Hello there!" exact-match easter egg, so neither of the
 * app's two special-case reply paths applies — only the first-letter keying
 * under test.
 */
const MESSAGE = 'Keyboard shortcuts are neat'
const KEYED_REPLY = 'Keyboards are really just aggressive finger trampolines.'

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test.describe('Chat offline replies', () => {
  test('sending a message shows it with the canned reply keyed by its first letter', async ({
    page,
  }) => {
    const chat = new PageManager(page).onChatPage()

    // Given: offline mode is active (Funny mode on) and the thread is empty.
    // The placeholder only renders once the history load has settled, so it
    // doubles as the readiness gate for the composer.
    await expect(chat.funnyModeCheckbox).toBeChecked()
    await expect(chat.emptyThreadPlaceholder).toBeVisible()

    // When: the user sends a message starting with "K"
    await chat.fillChatInput(MESSAGE)
    await chat.sendMessage()

    // Then: the transcript shows the user's message and the K-keyed reply
    await expect(chat.userMessage).toHaveText(MESSAGE)
    await expect(chat.assistantMessage).toHaveText(KEYED_REPLY)
  })
})

import { expect, test } from '@playwright/test'
import { PageManager } from './pages/pageManager'

/**
 * The first letter of MESSAGE is what picks the reply, so 'W' selects the 'W'
 * line. The message deliberately starts with a plain letter, holds no '?',
 * and is neither 'Hello there!' nor 'Help' — each of those routes the send
 * down a different reply path than the first-letter one under test.
 *
 * EXPECTED_REPLY is written out by hand rather than imported from
 * src/data/funnyReplies.ts: importing the app's own constant would make this
 * assertion agree with any regression to it.
 */
const MESSAGE = 'Wookiee cookies'
const EXPECTED_REPLY = 'White lemmings do not exist in the modern digital era'

test.describe('Chat — offline (Funny) mode', () => {
  test('sending a message shows it with the canned reply keyed by its first letter', async ({
    page,
  }) => {
    // Given: client-side storage is empty. Isolation has to come from the
    // fresh context Playwright gives each test — the app mirrors every
    // exchange into localStorage under 'ai-assistant-chat-history-v1', and
    // neither a reload nor the Reset Chat button clears that key.
    const requests: string[] = []
    const chatWrites: string[] = []
    page.on('request', (request) => {
      requests.push(request.url())
      if (request.method() === 'POST' && request.url().includes('/api/chat')) {
        chatWrites.push(request.url())
      }
    })

    await page.goto('/')

    const chat = new PageManager(page).onChatPage()

    // Given: a settled, empty transcript with offline (Funny) mode already on
    await expect(chat.emptyPlaceholder).toBeVisible()
    await expect(chat.funnyModeCheckbox).toBeChecked()
    await expect(chat.sendButton).toBeDisabled()

    // When: the user types a message and sends it
    await chat.fillChatInput(MESSAGE)
    await expect(chat.sendButton).toBeEnabled()
    await chat.sendMessage()

    // Then: wait out the pending "Thinking…" bubble, so the assertion below
    // reads the settled transcript rather than the placeholder
    await expect(chat.assistantMessage).toBeVisible()
    await expect(chat.loadingIndicator).not.toBeAttached()
    await expect(chat.sendButton).toBeDisabled()

    // Then: the transcript holds the user's message followed by the reply the
    // message's first letter keys to — exact text, exact order, nothing else
    await expect(chat.transcriptBubbles).toHaveText([MESSAGE, EXPECTED_REPLY])

    // Then: that reply came from nowhere but the browser. The bootstrap call
    // the app makes on load proves this observer sees the app's API traffic,
    // so the empty chatWrites below is a real absence and not a dead listener.
    expect(requests.filter((url) => url.includes('/api/messages'))).not.toHaveLength(0)
    expect(chatWrites).toHaveLength(0)
  })
})

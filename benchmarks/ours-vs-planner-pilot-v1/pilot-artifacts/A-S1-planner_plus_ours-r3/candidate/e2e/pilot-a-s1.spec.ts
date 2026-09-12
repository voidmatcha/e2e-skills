import { expect, test } from '@playwright/test'
import { PageManager } from './pages/pageManager'

/**
 * Scenario A-S1 — offline mode canned reply.
 *
 * "Offline mode" is this app's default-on "Funny mode": it answers entirely
 * client-side with a canned line picked by the first letter of the message,
 * and puts no chat request on the wire.
 *
 * MESSAGE is a plain statement so it stays on the letter-keyed path. A '?'
 * routes to the app-assistant topic replies, the exact string 'Help' routes to
 * the help menu, and the exact string 'Hello there!' is special-cased to
 * 'GENERAL KENOBI!!' — that last one is what e2e/tests/chat.spec.ts already
 * covers, so it is deliberately avoided here. EXPECTED_REPLY is the 'Z' entry
 * of FUNNY_REPLIES_BY_LETTER (src/data/funnyReplies.ts), observed live for
 * this message; sending 'Quiet morning at dawn' instead returns the 'Q' entry,
 * which is what makes this an assertion about the first letter rather than
 * about the rest of the sentence.
 */
const MESSAGE = 'Zebra crossing at dawn'
const EXPECTED_REPLY = 'ZIP files are introverted folders wearing compression hoodies.'

test.describe('Chat — offline mode', () => {
  test('sending a message shows it with the canned reply keyed by its first letter', async ({
    page,
  }) => {
    // Given: a fresh context (so client-side storage starts empty) on the chat
    // screen, with browser traffic recorded from before the first navigation.
    const requestUrls: string[] = []
    const chatRequests: string[] = []
    page.on('request', (request) => {
      requestUrls.push(request.url())
      if (request.method() === 'POST' && request.url().includes('/api/chat')) {
        chatRequests.push(request.url())
      }
    })

    await page.goto('/')

    const chat = new PageManager(page).onChatPage()

    // The composer starts disabled behind a "Loading…" placeholder until the
    // bootstrap history fetch settles, so gate on readiness before acting.
    await expect(chat.funnyModeCheckbox).toBeEnabled({ timeout: 15_000 })
    await expect(chat.emptyThreadPlaceholder).toBeVisible()
    // Offline mode is the default, but assert it rather than assume it: an
    // unchecked toggle would send this message over the network instead, and
    // the test would then be green about the wrong code path.
    await expect(chat.funnyModeCheckbox).toBeChecked()

    // When: the user sends a plain statement.
    await chat.fillChatInput(MESSAGE)
    await chat.sendMessage()

    // Then: the transcript holds exactly the user's message and exactly the
    // reply keyed by its first letter. The single-element array form also
    // pins the cardinality, so a duplicated or leaked-in message fails here.
    await expect(chat.userMessages).toHaveText([MESSAGE])
    await expect(chat.assistantMessages).toHaveText([EXPECTED_REPLY])

    // ...and offline means offline: no chat request left the browser. The
    // first assertion keeps the second honest — it proves the listener really
    // was attached and capturing, so an empty chatRequests list is evidence of
    // absence rather than evidence of a dead listener.
    expect(requestUrls.filter((url) => url.includes('/api/messages'))).not.toHaveLength(0)
    expect(chatRequests).toEqual([])
  })
})

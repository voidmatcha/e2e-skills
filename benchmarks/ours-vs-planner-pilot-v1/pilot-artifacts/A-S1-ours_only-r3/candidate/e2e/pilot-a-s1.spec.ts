import { expect, test } from '@playwright/test'
import { PageManager } from './pages/pageManager'

/**
 * Funny mode is the app's offline mode: the reply is picked from a canned
 * table keyed by the first letter of the message, with no network call.
 *
 * The existing chat spec only covers 'Hello there!', which hits the exact-string
 * special case and never reaches the letter table — so the keyed path is what
 * this spec pins down.
 */
const MESSAGE = 'Zebras ignore deadlines.'
const EXPECTED_REPLY =
  'ZIP files are introverted folders wearing compression hoodies.'

test.describe('Chat — offline (Funny) mode', () => {
  test('sending a message shows the user message and the letter-keyed canned reply', async ({
    page,
  }) => {
    /* Offline means offline. Recording every POST — rather than only the ones
     * whose path looks like the chat endpoint — keeps the endpoint spelling out
     * of this check's trust boundary: turning Funny mode off POSTs to /api/chat,
     * and any other write escaping the browser would fail here too. */
    const postRequests: string[] = []
    page.on('request', (request) => {
      if (request.method() === 'POST') {
        postRequests.push(`${request.method()} ${request.url()}`)
      }
    })

    await page.goto('/')

    const chat = new PageManager(page).onChatPage()

    // Preconditions, asserted rather than assumed: offline mode is on and the
    // transcript starts empty on a fresh context.
    await expect(chat.funnyModeCheckbox).toBeEnabled({ timeout: 15_000 })
    await expect(chat.funnyModeCheckbox).toBeChecked()
    await expect(chat.emptyStatePlaceholder).toBeVisible()

    await chat.fillChatInput(MESSAGE)
    await expect(chat.sendButton).toBeEnabled()
    await chat.sendMessage()

    // Settled-state gate: offline mode appends exactly one reply, so waiting
    // for it to exist means the text assertions below read a terminal
    // transcript instead of a half-rendered one. Asserting presence (rather
    // than the placeholder's absence) also means a renamed test id fails here
    // rather than passing against an empty collection.
    await expect(chat.assistantMessages).toHaveCount(1)

    // The array form pins the whole transcript: exactly one bubble on each
    // side, each with exactly this text.
    await expect(chat.userMessages).toHaveText([MESSAGE])
    await expect(chat.assistantMessages).toHaveText([EXPECTED_REPLY])

    expect(postRequests).toEqual([])
  })
})

import { expect, test } from '@playwright/test'
import { PageManager } from './pages/pageManager'

/**
 * A plain statement, chosen so it actually reaches the letter-keyed offline
 * path: it contains no '?' (which routes to the in-app assistant instead) and
 * it is not the exact string 'Hello there!' (which short-circuits to the
 * GENERAL KENOBI reply before the letter table is ever consulted — that
 * short-circuit is what e2e/tests/chat.spec.ts already covers).
 */
const MESSAGE = 'Kittens rule the internet.'

/**
 * The 'K' entry of the app's canned reply table, keyed by the first letter of
 * MESSAGE. Verified live before this test was written: a different K message
 * ('Kangaroos box professionally.') returns this same string, while
 * 'Ducks are fine.' returns the 'D' entry instead — so the reply really is
 * keyed by the letter, not by the message text.
 */
const LETTER_KEYED_REPLY = 'Keyboards are really just aggressive finger trampolines.'

/** Comfortably longer than the app's FUNNY_REPLY_DELAY_MS (120ms). */
const PAST_REPLY_DELAY_MS = 200

test.describe('Chat offline mode', () => {
  test('sending a message shows it and the letter-keyed canned reply in the transcript', async ({
    page,
  }) => {
    const chat = new PageManager(page).onChatPage()

    // Given: a fresh profile on the chat screen, settled past its initial load.
    // The clock is frozen up front so the reply timer below cannot fire on its
    // own — see the pending-state assertion for why that matters.
    await page.clock.install()
    await page.goto('/')
    await expect(chat.messageInput).toBeEnabled()
    await expect(chat.userMessages).toHaveCount(0)
    await expect(chat.assistantMessages).toHaveCount(0)

    // and: offline mode ("Funny mode") is on. Assert it rather than assume it —
    // otherwise a regression that flips the default would quietly exercise the
    // network-backed path and this test would still be named "offline mode".
    await expect(chat.funnyModeCheckbox).toBeChecked()

    // When: the user sends the message.
    await chat.fillChatInput(MESSAGE)
    await expect(chat.sendButton).toBeEnabled()
    await chat.sendMessage()

    // Then: the pending placeholder is showing. With the clock frozen this is a
    // stable state rather than a ~120ms window, so asserting it is not a race.
    // It also earns the absence assertion further down: without this line, that
    // one would be satisfied by zero matches and would keep passing if the
    // placeholder's test id were ever renamed.
    await expect(chat.loadingIndicator).toHaveCount(1)

    // and: once the reply timer is allowed to fire, the exchange settles. The
    // placeholder carries its own test id, so the assistant count can only be
    // satisfied by a real reply bubble, never by the pending one.
    await page.clock.runFor(PAST_REPLY_DELAY_MS)
    await expect(chat.assistantMessages).toHaveCount(1)
    await expect(chat.loadingIndicator).toHaveCount(0)

    // and: the transcript holds exactly the user's message and the one canned
    // reply keyed by its first letter. The exact counts make a duplicated or
    // echoed render fail here instead of passing a presence-only check.
    await expect(chat.userMessages).toHaveCount(1)
    await expect(chat.userMessages).toHaveText(MESSAGE)
    await expect(chat.assistantMessages).toHaveText(LETTER_KEYED_REPLY)
  })
})

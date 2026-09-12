import { expect, test } from '@playwright/test'
import { PageManager } from './pages/pageManager'

/**
 * Offline mode ("Funny mode", on by default) answers locally: the first letter
 * of the message picks a canned reply from a fixed A–Z table, with no backend
 * call at all. The two messages below start with different letters, so a reply
 * table that had collapsed to a single constant would not satisfy both.
 *
 * Neither message contains "?", so the in-app assistant never intercepts them
 * (it only answers questions), and neither is the exact string "Hello there!",
 * which has its own special-cased reply — both would bypass the letter table.
 *
 * Expected replies are written out literally rather than imported from
 * src/data/funnyReplies.ts: importing them would make the test agree with the
 * app by construction, whatever the table said.
 */
const W_MESSAGE = 'Waffles are structurally sound breakfast architecture.'
const W_REPLY = 'White lemmings do not exist in the modern digital era'
const D_MESSAGE = 'Ducks outnumber my deadlines this week.'
const D_REPLY = 'Ducks think breadcrumbs are cryptocurrency with excellent UX.'

test.describe('Offline mode chat replies', () => {
  test('letter-keyed canned reply follows each message into the transcript', async ({
    page,
  }) => {
    const chat = new PageManager(page).onChatPage()

    await page.goto('/')

    // The composer stays disabled until the history fetch settles, so waiting
    // on the empty-thread placeholder (rather than on the input alone) gates
    // the run on a ready *and* empty transcript.
    await expect(chat.emptyThreadPlaceholder).toBeVisible()
    await expect(chat.funnyModeCheckbox).toBeEnabled()
    // Offline mode is the default; assert it rather than toggling it, so a
    // regression that silently defaults to backend mode fails here.
    await expect(chat.funnyModeCheckbox).toBeChecked()

    await chat.fillChatInput(W_MESSAGE)
    await chat.sendMessage()

    await expect(chat.userMessages).toHaveText([W_MESSAGE])
    await expect(chat.assistantMessages).toHaveText([W_REPLY])

    await chat.fillChatInput(D_MESSAGE)
    await chat.sendMessage()

    // Settled state: offline mode appends exactly one reply per message and
    // nothing touches the transcript afterwards, so once the second reply has
    // landed the list below is final rather than still filling in.
    await expect(chat.assistantMessages).toHaveCount(2)

    // Array form pins order, exact text and count together: an extra, missing
    // or reordered bubble fails, and the second reply differing from the first
    // is what shows the reply is keyed off the message rather than fixed.
    await expect(chat.userMessages).toHaveText([W_MESSAGE, D_MESSAGE])
    await expect(chat.assistantMessages).toHaveText([W_REPLY, D_REPLY])
  })
})

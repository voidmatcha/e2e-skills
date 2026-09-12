import type { Locator, Page } from '@playwright/test'

export class ChatHistoryPage {
  /** Shell */
  readonly heading: Locator
  readonly emptyState: Locator

  /** Toolbar */
  readonly deleteHistoryButton: Locator

  /** Archive */
  readonly exchangeRows: Locator

  constructor(page: Page) {
    this.heading = page.getByRole('heading', {
      name: 'Message history',
      level: 2,
    })
    this.emptyState = page.getByText(
      'No history yet. Send a message in Chat to build your archive.',
    )
    this.deleteHistoryButton = page.getByRole('button', {
      name: 'Delete history',
    })
    // One <li> per stored exchange. The cells inside a row ("You", the user
    // text, "Assistant", the reply) are unnamed divs with no test hooks, and
    // the role labels repeat verbatim once a second exchange exists — so rows
    // are addressed here and callers narrow by message content instead.
    this.exchangeRows = page.getByRole('listitem')
  }
}

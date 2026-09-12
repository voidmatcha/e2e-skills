import type { Locator, Page } from '@playwright/test'

export class ChatHistoryPage {
  /** Screen */
  readonly heading: Locator
  readonly emptyState: Locator

  /** Toolbar */
  readonly deleteHistoryButton: Locator

  /** Archive */
  readonly exchangeItems: Locator

  constructor(page: Page) {
    this.heading = page.getByRole('heading', { name: 'Message history' })
    this.emptyState = page.getByText(
      'No history yet. Send a message in Chat to build your archive.',
    )

    this.deleteHistoryButton = page.getByRole('button', {
      name: 'Delete history',
    })

    // Every stored exchange is one <li> of the day's list; the screen has no
    // other list, so the listitem role addresses history entries on its own.
    this.exchangeItems = page.getByRole('listitem')
  }
}

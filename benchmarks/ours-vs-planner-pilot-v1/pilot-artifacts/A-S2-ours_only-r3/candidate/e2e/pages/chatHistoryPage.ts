import type { Locator, Page } from '@playwright/test'

/** localStorage key the app persists chat exchanges under. */
export const HISTORY_STORAGE_KEY = 'ai-assistant-chat-history-v1'

export class ChatHistoryPage {
  private readonly page: Page

  /** Shell */
  readonly heading: Locator
  readonly deleteHistoryButton: Locator

  /** Archive */
  readonly exchangeItems: Locator
  readonly emptyState: Locator

  constructor(page: Page) {
    this.page = page

    this.heading = page.getByRole('heading', {
      name: 'Message history',
      level: 2,
    })
    this.deleteHistoryButton = page.getByRole('button', {
      name: 'Delete history',
    })

    // Scoped to the archive container so the day lists are the only source of
    // listitems — the surrounding layout is free to grow its own lists later.
    this.exchangeItems = page.locator('.history-days').getByRole('listitem')
    this.emptyState = page.getByText(
      'No history yet. Send a message in Chat to build your archive.',
    )
  }

  /**
   * Deleting asks for confirmation through a native `window.confirm`, which
   * Playwright dismisses automatically unless a handler is registered — so the
   * handler has to be in place before the click, or nothing is deleted.
   */
  async deleteHistoryAndConfirm() {
    this.page.once('dialog', (dialog) => dialog.accept())
    await this.deleteHistoryButton.click()
  }

  /** Reads the persisted archive straight from the storage boundary. */
  async readStoredExchanges(): Promise<unknown[] | null> {
    return await this.page.evaluate((key) => {
      const raw = localStorage.getItem(key)
      return raw === null ? null : (JSON.parse(raw) as unknown[])
    }, HISTORY_STORAGE_KEY)
  }
}

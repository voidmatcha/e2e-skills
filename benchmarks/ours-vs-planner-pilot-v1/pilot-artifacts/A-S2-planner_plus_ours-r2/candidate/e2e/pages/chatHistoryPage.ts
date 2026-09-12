import type { Locator, Page } from '@playwright/test'

export class ChatHistoryPage {
  private readonly page: Page

  /** Shell */
  readonly heading: Locator
  readonly deleteHistoryButton: Locator

  /** Archive */
  readonly emptyState: Locator
  readonly exchangeEntries: Locator

  constructor(page: Page) {
    this.page = page
    this.heading = page.getByRole('heading', {
      name: 'Message history',
      level: 2,
    })
    this.deleteHistoryButton = page.getByRole('button', {
      name: 'Delete history',
    })
    this.emptyState = page.getByText(
      'No history yet. Send a message in Chat to build your archive.',
    )
    this.exchangeEntries = page.getByRole('listitem')
  }

  /**
   * Deleting is guarded by a native window.confirm(), so the handler has to be
   * registered before the click — otherwise the click never settles and the
   * cleared state can never be observed. Returns the confirm text so the spec
   * can assert on it and get a real diagnostic instead of a hang.
   */
  async deleteHistoryAndConfirm(): Promise<string> {
    const confirmMessage = new Promise<string>((resolve) => {
      this.page.once('dialog', (dialog) => {
        resolve(dialog.message())
        void dialog.accept()
      })
    })
    await this.deleteHistoryButton.click()
    return confirmMessage
  }
}

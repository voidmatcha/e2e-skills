import type { Locator, Page } from '@playwright/test'

export class ChatPage {
  /** Shell & status */
  readonly funnyModeCheckbox: Locator
  readonly loadingLabel: Locator
  readonly chatWindow: Locator
  readonly messageList: Locator
  readonly sectionDivider: Locator

  /** Composer */
  readonly messageInput: Locator
  readonly sendButton: Locator
  readonly resetChatButton: Locator

  /** Thread */
  readonly chatMessageFirst: Locator
  readonly chatMessageFirstReply: Locator

  /**
   * Thread, addressed by test id. LoadingMessage carries its own
   * data-testid ("loading-indicator") rather than the assistant one, so
   * unlike the class-based locators above these can never bind to the
   * transient "Thinking…" placeholder and need no :not() qualifier.
   */
  readonly emptyPlaceholder: Locator
  readonly transcriptBubbles: Locator
  readonly assistantMessage: Locator
  readonly loadingIndicator: Locator

  constructor(page: Page) {
    this.funnyModeCheckbox = page.getByRole('checkbox', {
      name: /funny mode/i,
    })
    this.loadingLabel = page.getByText('Loading…')
    this.chatWindow = page.locator('.chat-window')
    this.messageList = page.locator('.chat-window__list')
    this.sectionDivider = page.locator('.chat-window__divider')

    this.messageInput = page.getByPlaceholder('Type a message…')
    this.sendButton = page.getByRole('button', { name: 'Send' })
    this.resetChatButton = page.getByRole('button', { name: 'Reset Chat' })

    this.chatMessageFirst = page
      .locator('.chat-message--user')
      .first()
      .locator('.chat-message__bubble')
    // Exclude .chat-message--loading: the "Thinking…" placeholder shares
    // .chat-message--assistant with the real reply while it's pending, so
    // an unqualified first() can transiently match the placeholder instead.
    this.chatMessageFirstReply = page
      .locator('.chat-message--assistant:not(.chat-message--loading)')
      .first()
      .locator('.chat-message__bubble')

    this.emptyPlaceholder = page.getByText('No messages yet.')
    // Direct test-id children of the list, in render order. The "No messages
    // yet."/"Loading…" placeholder is a <p> with no test id, so it never
    // matches; the pending "Thinking…" bubble does match while it is mounted,
    // which is why callers gate on loadingIndicator before asserting on this.
    this.transcriptBubbles = page.locator('.chat-window__list > [data-testid]')
    this.assistantMessage = page.getByTestId('message-assistant')
    this.loadingIndicator = page.getByTestId('loading-indicator')
  }

  async sendMessage() {
    await this.sendButton.click()
  }

  async fillChatInput(message: string) {
    await this.messageInput.fill(message)
  }

  async getChatMessageFirstText() {
    return await this.chatMessageFirst.textContent()
  }

  async getChatMessageFirstReplyText() {
    return await this.chatMessageFirstReply.textContent()
  }
}

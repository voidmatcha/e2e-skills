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

  /** Transcript, addressed by the test ids the app renders on each bubble.
   * The pending "Thinking…" placeholder carries its own `loading-indicator`
   * id rather than `message-assistant`, so these never match the placeholder. */
  readonly emptyStatePlaceholder: Locator
  readonly userMessages: Locator
  readonly assistantMessages: Locator

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

    this.emptyStatePlaceholder = page.getByText('No messages yet.')
    this.userMessages = page.getByTestId('message-user')
    this.assistantMessages = page.getByTestId('message-assistant')
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

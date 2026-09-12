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

  /** Thread, addressed by the components' own test hooks rather than by
   * styling classes. `loading-indicator` is a distinct test id from
   * `message-assistant`, so `assistantMessages` can never transiently match
   * the "Thinking..." placeholder. */
  readonly userMessages: Locator
  readonly assistantMessages: Locator
  readonly emptyThreadPlaceholder: Locator

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

    this.userMessages = page.getByTestId('message-user')
    this.assistantMessages = page.getByTestId('message-assistant')
    this.emptyThreadPlaceholder = page.getByText('No messages yet.')
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

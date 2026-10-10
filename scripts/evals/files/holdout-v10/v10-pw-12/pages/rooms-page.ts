import type { Locator, Page } from '@playwright/test';

export class RoomsPage {
  constructor(private readonly page: Page) {}

  room(number: string): Locator {
    return this.page.getByTestId(`room-${number}`);
  }

  async requestLinen(number: string): Promise<void> {
    await this.room(number).getByRole('button', { name: 'Request linen', exact: true }).click();
  }
}

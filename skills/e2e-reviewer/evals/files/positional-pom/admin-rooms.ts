import type { Locator, Page } from '@playwright/test';

export class AdminRooms {
	constructor(private readonly page: Page) {}

	getRoomRow(name: string): Locator {
		return this.page.getByRole('row', { name, exact: true });
	}

	getRoomMessagesCountCell(name: string): Locator {
		return this.getRoomRow(name).getByRole('cell').nth(3);
	}

	getCellByIndex(name: string, index: number): Locator {
		return this.getRoomRow(name).getByRole('cell').nth(index);
	}
}

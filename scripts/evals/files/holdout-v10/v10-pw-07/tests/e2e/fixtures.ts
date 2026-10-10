import { test as base, expect } from '@playwright/test';

export const test = base.extend<{ memberCard: string }>({
  memberCard: async ({}, use) => {
    await use('LIB-20931');
  },
});

export { expect };

// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  use: { baseURL: 'http://localhost:3000', actionTimeout: 10_000 },
});

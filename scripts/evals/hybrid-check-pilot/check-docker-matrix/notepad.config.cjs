// SPDX-License-Identifier: Apache-2.0
module.exports = {
  testDir: __dirname, testMatch: 'notepad.spec.cjs', workers: 1, retries: 0,
  timeout: 20000, expect: {timeout: 1200}, outputDir: '/test-out/trace',
  use: {headless: true, browserName: 'chromium', serviceWorkers: 'block', trace: 'on', actionTimeout: 5000},
};

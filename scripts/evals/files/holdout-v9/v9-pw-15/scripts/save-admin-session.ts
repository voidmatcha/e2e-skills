// Manual step: opens a headed browser; sign in as the admin by hand, then press Enter.
import { chromium } from '@playwright/test';
import { createInterface } from 'node:readline/promises';

async function main() {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();
  await page.goto('http://localhost:5173/login');
  const prompt = createInterface({ input: process.stdin, output: process.stdout });
  await prompt.question('Sign in, then press Enter to save the session... ');
  await page.context().storageState({ path: 'playwright/.auth/admin.json' });
  await browser.close();
}

void main();

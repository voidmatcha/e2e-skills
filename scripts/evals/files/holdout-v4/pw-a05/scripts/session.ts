import { chromium } from '@playwright/test';

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('/sign-in');
  await page.context().storageState({ path: '.state/member.json' });
  await browser.close();
}

void main();

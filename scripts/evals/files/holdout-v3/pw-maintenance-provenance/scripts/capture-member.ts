import { chromium } from '@playwright/test';

const browser = await chromium.launch({ headless: false });
const page = await browser.newPage();
await page.goto('/login');
await page.pause();
await page.context().storageState({ path: '.auth/member-manual.json' });
await browser.close();

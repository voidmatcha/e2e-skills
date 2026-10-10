#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { TextDecoder } = require('node:util');

const MAX_TARGET_BYTES = 64 * 1024;
const MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024;
const ALLOWED_ENVIRONMENT = new Set(['HOME', 'PATH']);

for (const name of Object.keys(process.env)) {
  if (!ALLOWED_ENVIRONMENT.has(name)) delete process.env[name];
}

function fail(message) {
  throw new Error(`raw-aria-snapshot: ${message}`);
}

function readTargetFrame() {
  if (process.argv.length !== 3 || process.argv[2] !== '--framed-stdin') {
    fail('use --framed-stdin; the target URL belongs on stdin');
  }
  const framed = fs.readFileSync(0);
  if (framed.length < 9 || framed[8] !== 0x0a) {
    fail('malformed target frame header');
  }
  const header = framed.subarray(0, 8).toString('ascii');
  if (!/^[0-9a-f]{8}$/.test(header)) {
    fail('malformed target frame length');
  }
  const length = Number.parseInt(header, 16);
  if (length > MAX_TARGET_BYTES) fail('target URL frame is too large');
  if (framed.length !== 9 + length) {
    fail('incomplete target frame or trailing bytes');
  }
  return new TextDecoder('utf-8', { fatal: true }).decode(
    framed.subarray(9)
  );
}

function effectivePort(url) {
  return url.port || (url.protocol === 'https:' ? '443' : '80');
}

function normalizedHost(host) {
  return host.replace(/^\[|\]$/g, '').toLowerCase();
}

function hasCanonicalNumericLoopbackAuthority(raw) {
  const match = /^(?:http|https):\/\/([^/?#]*)/.exec(raw);
  if (!match) return false;
  return /^(?:127\.0\.0\.1|\[::1\])(?::[0-9]+)?$/.test(match[1]);
}

function assertSafeNavigation(raw, approved) {
  const candidate = new URL(raw);
  if (
    !['http:', 'https:'].includes(candidate.protocol) ||
    candidate.username ||
    candidate.password ||
    candidate.hash ||
    candidate.hostname !== approved.hostname ||
    candidate.protocol !== approved.protocol ||
    effectivePort(candidate) !== effectivePort(approved)
  ) {
    fail('blocked navigation outside approved origin');
  }
  if (
    !hasCanonicalNumericLoopbackAuthority(raw) ||
    !['127.0.0.1', '::1'].includes(
      normalizedHost(approved.hostname)
    )
  ) {
    fail('raw-ARIA fallback requires 127.0.0.1 or ::1');
  }
}

async function captureSnapshot() {
  const target = readTargetFrame();
  const approved = new URL(target);
  assertSafeNavigation(target, approved);

  const projectRequire = createRequire(
    path.join(process.cwd(), '.e2e-skills-raw-aria-loader.cjs')
  );
  const { chromium } = projectRequire('@playwright/test');
  let browser;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext({
      javaScriptEnabled: false,
      serviceWorkers: 'block',
    });
    await context.route('**/*', async route => {
      try {
        assertSafeNavigation(route.request().url(), approved);
        await route.continue();
      } catch {
        await route.abort('blockedbyclient');
      }
    });
    const page = await context.newPage();
    await page.goto(approved.href, { waitUntil: 'domcontentloaded' });
    assertSafeNavigation(page.url(), approved);
    const snapshot = String(await page.locator('body').ariaSnapshot());
    if (Buffer.byteLength(snapshot, 'utf8') > MAX_SNAPSHOT_BYTES) {
      fail('ARIA snapshot exceeds the output limit');
    }
    process.stdout.write(snapshot.endsWith('\n') ? snapshot : `${snapshot}\n`);
  } finally {
    if (browser) await browser.close();
  }
}

captureSnapshot().catch(error => {
  console.error(String(error));
  process.exitCode = 1;
});

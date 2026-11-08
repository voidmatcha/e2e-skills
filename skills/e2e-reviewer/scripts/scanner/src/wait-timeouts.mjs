// SPDX-License-Identifier: Apache-2.0
// Project-wide inputs for the #3 swallowed-wait effective-timeout check.
// Static declarations only: nothing is evaluated, and every gap in what the
// scanner can see makes the result `known: false`, never a defaults claim.
//
// Playwright Test sets every context's default action and navigation timeout
// to `use.actionTimeout || 0` and `use.navigationTimeout || 0` (playwright
// lib/index.js `_setupContextOptions`), so with neither configured a
// `waitFor()` without its own `timeout` waits until the test timeout fails the
// test. A `.catch` on that call cannot turn a missing target into a pass.
import fs from 'node:fs';
import path from 'node:path';

// Unknowns on these fields cannot change an action or navigation timeout.
const IRRELEVANT_FIELDS = new Set(['testDir', 'testMatch', 'testIgnore', 'retries', 'timeout', 'use.baseURL']);
const BLOCKING_PROJECT_UNKNOWNS = new Set(['CONFIG_CONTEXT_UNAVAILABLE', 'CONFIG_ROOT_NOT_FOUND', 'CONFIG_COUNT_LIMIT', 'CONFIG_MULTIPLE_ROOT_FILES']);
// Any of these in a scanned source can set a default timeout, change which
// runtime defaults apply, or import an unseen fixture that might.
const OVERRIDES = [
  [/\bsetDefault(?:Navigation)?Timeout\b/, 'a scanned source calls setDefaultTimeout or setDefaultNavigationTimeout'],
  [/\b(?:actionTimeout|navigationTimeout)\b/, 'a scanned source names actionTimeout or navigationTimeout'],
  [/\b(?:launch|launchPersistentContext|launchServer|connect|connectOverCDP)\s*\(/, 'a scanned source launches or connects a browser directly'],
  [/\bfrom\s*['"]playwright(?:-core)?['"]|\brequire\(\s*['"]playwright(?:-core)?['"]\s*\)/, 'a scanned source imports the playwright library outside Playwright Test'],
  [/\b_electron\b/, 'a scanned source drives Electron'],
];
const ALTERNATE_CONFIG = /^(?:.*playwright.*\.config|.*\.config.*playwright.*|playwright(?:[-_.].+)?)\.(?:[cm]?[jt]s)$/i;
const FIXTURE_IMPORT = /\bimport\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g;

function unknown(reason) { return { known: false, reason }; }

function alternateConfig(directory, keep) {
  let names;
  try { names = fs.readdirSync(directory); } catch { return 'the configuration directory could not be listed'; }
  const other = names.find(name => name !== keep && ALTERNATE_CONFIG.test(name));
  return other ? `another Playwright configuration file (${other}) may be the one the runner uses` : null;
}

export function playwrightWaitTimeouts({ configurationAnalysis, sources } = {}) {
  if (!configurationAnalysis || !(sources instanceof Map)) return unknown('no configuration analysis');
  const projectUnknown = (configurationAnalysis.unknowns || []).find(item => BLOCKING_PROJECT_UNKNOWNS.has(item?.code));
  if (projectUnknown) return unknown(`configuration ${projectUnknown.code}`);
  const records = (configurationAnalysis.configurations || []).filter(item => item.framework === 'playwright');
  if (records.length !== 1) return unknown(records.length ? 'more than one Playwright configuration' : 'no Playwright configuration was found');
  const [record] = records;
  const blocking = record.unknowns.find(item => !IRRELEVANT_FIELDS.has(item.field));
  if (blocking) return unknown(`${path.basename(record.path)} has ${blocking.code}${blocking.field ? ` at ${blocking.field}` : ''}`);
  for (const directory of new Set([record.baseDirectory, configurationAnalysis.projectRoot].filter(Boolean))) {
    const alternate = alternateConfig(directory, path.basename(record.path));
    if (alternate) return unknown(alternate);
  }
  for (const [file, bytes] of sources) {
    // The configuration itself was interpreted above.
    if (path.resolve(file) === path.resolve(record.path)) continue;
    const text = Buffer.isBuffer(bytes) ? bytes.toString('utf8') : String(bytes);
    for (const [pattern, reason] of OVERRIDES) if (pattern.test(text)) return unknown(`${reason} (${path.basename(file)})`);
    for (const match of text.matchAll(FIXTURE_IMPORT)) {
      const names = match[1].split(',').map(item => item.trim().split(/\s+as\s+/)[0].trim());
      const module = match[2];
      if (names.includes('test') && !module.startsWith('.') && !['@playwright/test', 'playwright/test'].includes(module))
        return unknown(`test is imported from package ${module}, whose fixtures are not scanned (${path.basename(file)})`);
    }
  }
  const value = field => record.observations.find(item => item.field === field)?.value;
  const actionTimeout = value('use.actionTimeout'), navigationTimeout = value('use.navigationTimeout');
  for (const [field, item] of [['use.actionTimeout', actionTimeout], ['use.navigationTimeout', navigationTimeout]])
    if (item !== undefined && typeof item !== 'number') return unknown(`${field} is not a number`);
  return { known: true, config: path.basename(record.path), actionTimeout: actionTimeout || 0, navigationTimeout: navigationTimeout || 0 };
}

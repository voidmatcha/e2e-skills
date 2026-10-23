// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';

test('retired backend controls fail before scanning or executing local configuration', () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-env-contract-')));
  try {
    const file = path.join(root, 'example.spec.ts'), marker = path.join(root, 'executed');
    fs.writeFileSync(file, "import {test} from '@playwright/test';test.only('focus',()=>{});\n");
    fs.writeFileSync(path.join(root, 'eslint.config.mjs'), `import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(marker)},'bad');export default [];`);
    const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('E2E_SMELL_')));
    const run = (extra, args = []) => spawnSync(process.execPath,
      [new URL('../src/cli.mjs', import.meta.url).pathname, '--scan', file, ...args],
      { env: { ...env, ...extra }, encoding: 'utf8', timeout: 15000 });
    for (const key of ['E2E_SMELL_ALLOW_PROJECT_ESLINT', 'E2E_SMELL_SCOPE_WATCH',
      'E2E_SMELL_MAX_RULE_HITS', 'E2E_SMELL_MAX_RULE_BYTES', 'E2E_SMELL_MAX_RULE_HITS_HARD',
      'E2E_SMELL_ESLINT_TIMEOUT_SECS', 'E2E_SMELL_RG_BIN', 'E2E_SMELL_NODE_BIN',
      'E2E_SMELL_NPX_BIN', 'E2E_SMELL_AST_GREP_BIN', 'E2E_SMELL_PYTHON_BIN',
      'E2E_SMELL_DISABLE_AST_GREP', 'E2E_SMELL_IGNORE_HOST_AST_GREP',
      'E2E_SMELL_NO_ESLINT_DOWNLOAD', 'E2E_SMELL_NO_AST_GREP_DOWNLOAD', 'E2E_SMELL_TYPO']) {
      const result = run({ [key]: 'private-value-must-not-leak' });
      assert.ifError(result.error);
      assert.equal(result.status, 2, key);
      assert.equal(result.stdout, '', key);
      assert.match(result.stderr, /INCOMPLETE: retired E2E_SMELL_/);
      assert.ok(!result.stderr.includes('private-value-must-not-leak'));
    }
    const inert = { E2E_SMELL_NO_ESLINT_DOWNLOAD: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1',
      E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_SCOPE_WATCH: 'off' };
    assert.deepEqual(JSON.parse(run(inert).stdout), JSON.parse(run({}).stdout));
    assert.equal(run({ E2E_SMELL_FAIL_ON: 'none' }).status, 0);
    assert.equal(run({ E2E_SMELL_FAIL_ON: 'none' }, ['--fail-on', 'p0']).status, 1);
    assert.equal(run({ E2E_SMELL_ALLOW_PROJECT_ESLINT: '1' }).status, 2);
    assert.equal(run({ E2E_SMELL_SCOPE_WATCH: 'strict' }).status, 2);
    assert.match(run(inert, ['--project-eslint', '--trust-project']).stderr, /conflicts with/);
    assert.equal(fs.existsSync(marker), false);
    assert.equal(fs.readFileSync(file, 'utf8'), "import {test} from '@playwright/test';test.only('focus',()=>{});\n");
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

test('packaged probe is byte-identical to the authoritative skill runner', () => {
  assert.deepEqual(fs.readFileSync(new URL('../scripts/run-probe.mjs', import.meta.url)),
    fs.readFileSync(new URL('../../../skills/e2e-reviewer/scripts/run-probe.mjs', import.meta.url)));
});

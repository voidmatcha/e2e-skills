// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

test('packaged probe closure is byte-identical to the authoritative skill runner', () => {
  for (const name of ['run-probe.mjs', 'probe-lifecycle.mjs', 'probe-anchor.mjs',
    'probe-cypress.mjs', 'probe-cypress-node.mjs']) {
    assert.deepEqual(fs.readFileSync(new URL(`../scripts/${name}`, import.meta.url)),
      fs.readFileSync(new URL(`../../../skills/e2e-reviewer/scripts/${name}`, import.meta.url)), name);
  }
});

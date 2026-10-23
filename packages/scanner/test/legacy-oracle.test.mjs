// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';

const fixture = new URL('../../../scripts/ci/fixtures/legacy-scanner/', import.meta.url);
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
test('frozen oracle restores every exact byte and mode outside the current product tree', () => {
  const manifest = JSON.parse(fs.readFileSync(new URL('manifest.json', fixture)));
  const scanner = legacyOracleFile();
  assert.ok(!scanner.startsWith(fileURLToPath(new URL('../../../', import.meta.url))));
  for (const item of manifest.files) {
    const file = legacyOracleFile(item.path), bytes = fs.readFileSync(file);
    assert.equal(sha(bytes), item.sha256, item.path);
    assert.equal(bytes.length, item.bytes);
    assert.equal(fs.statSync(file).mode & 0o777, item.mode);
  }
  assert.match(fs.readFileSync(scanner, 'utf8'), /run_check P0 '#7'/);
  assert.throws(() => legacyOracleFile('../scan.sh'), /unknown legacy oracle file/);
});

test('corrupt manifest or archive is rejected before materialization', () => {
  for (const name of ['manifest.json', 'oracle.json.gz']) {
    const root = fs.mkdtempSync(path.join(fs.realpathSync('/tmp'), 'oracle-corrupt-'));
    try {
      for (const file of ['oracle.mjs', 'manifest.json', 'oracle.json.gz'])
        fs.copyFileSync(new URL(file, fixture), path.join(root, file));
      fs.appendFileSync(path.join(root, name), 'corrupt');
      const result = spawnSync(process.execPath, ['--input-type=module', '-e',
        `import {legacyOracleFile} from ${JSON.stringify(pathToFileURL(path.join(root, 'oracle.mjs')).href)};legacyOracleFile();`],
      { encoding: 'utf8', env: { PATH: '/usr/bin:/bin' } });
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /legacy oracle (?:manifest|archive) digest mismatch/);
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  }
});

test('changed helper is rejected on next access and normal exit removes the private copy', () => {
  const moduleURL = new URL('oracle.mjs', fixture).href;
  const script = `import fs from 'node:fs';import path from 'node:path';
    import {legacyOracleFile} from ${JSON.stringify(moduleURL)};
    const scanner=legacyOracleFile();console.log(path.dirname(scanner));
    fs.appendFileSync(legacyOracleFile('scope-source.sh'),'drift');
    try {legacyOracleFile();process.exitCode=99;} catch(error) {
      if(!error.message.includes('extracted file changed'))throw error;
    }`;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', script],
    { encoding: 'utf8', env: { PATH: '/usr/bin:/bin', TMPDIR: '/must-not-be-used' } });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.existsSync(result.stdout.trim()), false);
});

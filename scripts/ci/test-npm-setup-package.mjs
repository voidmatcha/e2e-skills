#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Pack the real npm artifact, install its locked dependencies without lifecycle scripts,
// and exercise it without installing skills or hosts.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { gunzipSync } from 'node:zlib';
import { buildSetupRuntime } from '../../packages/scanner/scripts/build-setup-runtime.mjs';
import { verifyRuntime } from '../../packages/scanner/src/setup-cli.mjs';
if (process.argv.slice(2).some(arg => arg !== '--keep') || process.argv.slice(2).length > 1) throw Error('Usage: node scripts/ci/test-npm-setup-package.mjs [--keep]');
const keep = process.argv.includes('--keep');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
function trustedFile(candidate, executable = false) {
  const resolved = fs.realpathSync(candidate), stat = fs.statSync(resolved);
  assert.ok(stat.isFile() && !(stat.mode & 0o022), 'runtime must be a regular file without group/other write permission');
  assert.ok(resolved !== root && !resolved.startsWith(root + path.sep), 'runtime must be outside the source checkout');
  if (executable) fs.accessSync(resolved, fs.constants.X_OK);
  return resolved;
}
const node = trustedFile(process.execPath, true);
const prefix = path.dirname(path.dirname(node));
const npm = [path.join(prefix, 'lib/node_modules/npm/bin/npm-cli.js'), path.join(prefix, 'share/nodejs/npm/bin/npm-cli.js'), '/opt/homebrew/lib/node_modules/npm/bin/npm-cli.js', '/usr/local/lib/node_modules/npm/bin/npm-cli.js', '/usr/lib/node_modules/npm/bin/npm-cli.js', '/usr/share/nodejs/npm/bin/npm-cli.js'].map(candidate => { try { return trustedFile(candidate); } catch { return null; } }).find(Boolean);
assert.ok(npm, 'trusted npm CLI is required for the package gate');
const temporary = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-npm-packed-')));
try {
  const author = path.join(temporary, 'author');
  buildSetupRuntime(root, author);
  const stage = path.join(author, 'packages/scanner'), packed = path.join(temporary, 'packed'), home = path.join(temporary, 'home'), extract = path.join(temporary, 'extract');
  for (const directory of [stage, packed, home, extract]) fs.mkdirSync(directory, { recursive: true });
  const userconfig = path.join(temporary, 'user.npmrc'), globalconfig = path.join(temporary, 'global.npmrc');
  fs.writeFileSync(userconfig, ''); fs.writeFileSync(globalconfig, '');
  const env = { PATH: '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin', HOME: home, TMPDIR: temporary, LANG: 'C', LC_ALL: 'C', CI: '1', NO_COLOR: '1', GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null', GIT_TERMINAL_PROMPT: '0' };
  const source = path.join(root, 'packages/scanner'), metadata = JSON.parse(fs.readFileSync(path.join(source, 'package.json'), 'utf8'));
  fs.copyFileSync(path.join(source, 'package.json'), path.join(stage, 'package.json'));
  for (const entry of metadata.files) {
    if (entry === 'setup-runtime/') continue;
    assert.ok(!path.isAbsolute(entry) && !entry.split('/').includes('..'), 'safe package allowlist path');
    fs.cpSync(path.join(source, entry), path.join(stage, entry), { recursive: true, dereference: false });
  }
  assert.equal(fs.existsSync(path.join(stage, 'setup-runtime')), false, 'author pack starts without generated payload');
  assert.equal(metadata.scripts.prepack, 'node scripts/build-setup-runtime.mjs');
  for (const hook of ['install', 'postinstall', 'prepare']) assert.equal(metadata.scripts[hook], undefined, 'no consumer setup lifecycle hook');
  function run(args, expected = 0, cwd = stage) {
    const result = spawnSync(node, args, { cwd, env, encoding: 'utf8', timeout: 60000, maxBuffer: 32 * 1024 * 1024 });
    if (result.error) throw result.error;
    assert.equal(result.status, expected, `command exit: ${args.join(' ')}\n${result.stderr}\n${result.stdout}`);
    return result.stdout;
  }
  const result = JSON.parse(run([npm, 'pack', '--json', '--offline', '--audit=false', '--fund=false', '--userconfig=' + userconfig, '--globalconfig=' + globalconfig, '--cache=' + path.join(temporary, 'npm-cache'), '--pack-destination=' + packed]));
  buildSetupRuntime(author, path.join(stage, 'setup-runtime'), { check: true });
  assert.equal(result.length, 1); assert.equal(path.basename(result[0].filename), result[0].filename);
  // Read the actual tar stream. Reject links, special files, unsafe paths and
  // unsupported metadata before creating any extracted file.
  const tar = gunzipSync(fs.readFileSync(path.join(packed, result[0].filename)), { maxOutputLength: 64 * 1024 * 1024 });
  const entries = new Map();
  const field = bytes => bytes.toString('utf8').replace(/\0.*$/s, '');
  const octal = bytes => { const raw = field(bytes).trim(); assert.match(raw, /^[0-7]*$/); return raw ? parseInt(raw, 8) : 0; };
  for (let offset = 0; offset + 512 <= tar.length;) {
    const header = tar.subarray(offset, offset + 512); offset += 512;
    if (header.every(byte => byte === 0)) { assert.ok(tar.subarray(offset).every(byte => byte === 0)); break; }
    const checksum = octal(header.subarray(148, 156));
    assert.equal([...header].reduce((sum, byte, index) => sum + (index >= 148 && index < 156 ? 32 : byte), 0), checksum, 'tar header checksum');
    const prefix = field(header.subarray(345, 500)), leaf = field(header.subarray(0, 100));
    const name = prefix ? prefix + '/' + leaf : leaf;
    assert.ok(name.startsWith('package/') && !name.includes('\\') && !name.split('/').some(part => part === '..' || part === '.'), 'safe package tar path: ' + name);
    const type = header[156], size = octal(header.subarray(124, 136)), mode = octal(header.subarray(100, 108)) & 0o777;
    assert.ok(type === 0 || type === 48 || type === 53, 'tar must contain only regular files/directories');
    assert.ok(offset + size <= tar.length, 'complete tar entry');
    if (type !== 53) { assert.ok(!entries.has(name), 'no duplicate tar paths'); entries.set(name, { bytes: Buffer.from(tar.subarray(offset, offset + size)), mode }); }
    offset += Math.ceil(size / 512) * 512;
  }
  const required = ['package.json', 'src/setup-cli.mjs', 'src/cli.mjs', 'src/check-cli.mjs', 'setup-runtime/inventory.json', 'setup-runtime/install.sh', 'setup-runtime/LICENSE', 'setup-runtime/NOTICE', 'setup-runtime/scripts/dev/setup.mjs', 'setup-runtime/scripts/dev/reinstall-skills.sh', 'setup-runtime/scripts/dev/vendor/smol-toml/index.cjs', 'setup-runtime/scripts/dev/vendor/smol-toml/LICENSE', 'setup-runtime/scripts/dev/vendor/smol-toml/provenance.json', 'guidance/test-authoring-memo.txt', 'guidance/test-failure-policy.txt'];
  for (const name of ['e2e-finding-verifier', 'e2e-failure-classifier']) required.push(`setup-runtime/.codex/agents/${name}.toml`, `setup-runtime/agents/${name}.md`);
  for (const name of ['cypress-debugger', 'e2e-reviewer', 'playwright-debugger', 'playwright-test-generator']) required.push(`setup-runtime/skills/${name}/SKILL.md`);
  for (const name of required) assert.ok(entries.has('package/' + name), 'packed closure missing ' + name);
  for (const name of entries.keys()) assert.ok(!/(?:^|\/)(?:node_modules|__pycache__|\.git|\.cache|\.pytest_cache|testbed|test-results|playwright-report|setup-runtime\.tmp)(?:\/|$)|^package\/test\/|\.local\.md$|\.py[co]$|(?:^|\/)\.DS_Store$|(?:^|\/)(?:auth\.json|\.npmrc)$/.test(name), 'private/development file packed: ' + name);
  for (const name of entries.keys()) {
    assert.ok(!/^package\/setup-runtime\/skills\/[^/]+\/evals(?:\/|$)/.test(name), 'skill evaluation fixtures must stay development-only: ' + name);
    assert.ok(!/(?:^|\/)(?:grep-patterns\.md|v3-adapter\.md|check\.py)$/.test(name), 'retired lookup or fixed-project pilot packed: ' + name);
  }
  assert.ok(entries.has('package/setup-runtime/skills/e2e-reviewer/scripts/run-probe.mjs'), 'portable mutation/fault executor remains installed');
  assert.deepEqual([...entries.keys()].sort(), result[0].files.map(file => 'package/' + file.path).sort(), 'npm file report matches actual tar');
  for (const [name, { bytes, mode }] of entries) {
    const target = path.join(extract, name); fs.mkdirSync(path.dirname(target), { recursive: true }); fs.writeFileSync(target, bytes, { flag: 'wx', mode }); fs.chmodSync(target, mode);
  }
  verifyRuntime(path.join(extract, 'package/setup-runtime'));
  // Exercise npm dependency resolution in the extracted consumer, not source node_modules.
  fs.copyFileSync(path.join(source, 'package-lock.json'), path.join(extract, 'package/package-lock.json'));
  run([npm, 'ci', '--ignore-scripts', '--audit=false', '--fund=false', '--registry=https://registry.npmjs.org', '--userconfig=' + userconfig, '--globalconfig=' + globalconfig, '--cache=' + path.join(temporary, 'npm-cache')], 0, path.join(extract, 'package'));
  const cli = path.join(extract, 'package/src/setup-cli.mjs');
  assert.match(run([cli, '--help']), /Usage: e2e-skills/); assert.deepEqual(fs.readdirSync(home), [], 'help leaves HOME untouched');
  for (const host of ['codex', 'claude']) {
    assert.match(run([cli, 'install', '--host', host, '--dry-run']), /Dry run: no files changed/);
    assert.deepEqual(fs.readdirSync(home), [], `${host} dry-run leaves HOME untouched`);
    const report = JSON.parse(run([cli, 'doctor', '--host', host], 1));
    assert.equal(report.host, host); assert.equal(report.agents.length, 2); assert.ok(report.requirements.length >= 6); assert.ok(report.next_steps.length);
    for (const key of ['session_tools', 'approval', 'browser']) assert.equal(report[key], 'UNKNOWN');
    assert.equal(report.server, 'NOT_CHECKED'); assert.deepEqual(fs.readdirSync(home), [], `${host} doctor leaves HOME untouched`);
  }
  const guided = path.join(temporary, 'guided-project'); fs.mkdirSync(guided);
  const preview = JSON.parse(run([cli, 'guidance', '--host', 'claude', '--project', guided, '--memo', '--policy', '--dry-run']));
  assert.equal(preview.file, 'CREATED'); assert.equal(preview.blocks.length, 2); assert.deepEqual(fs.readdirSync(guided), [], 'guidance dry-run writes nothing');
  run([cli, 'guidance', '--host', 'claude', '--project', guided], 2); assert.deepEqual(fs.readdirSync(guided), [], 'guidance without --memo/--policy writes nothing');
  console.log(`npm setup package: ${entries.size} actual packed files; integrity, help, both host dry-runs, read-only doctors and guidance dry-run passed`);
} finally {
  if (keep) console.log('Retained owned package fixture: ' + temporary);
  else fs.rmSync(temporary, { recursive: true, force: true });
}

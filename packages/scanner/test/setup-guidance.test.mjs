// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GUIDANCE, guidanceText, main } from '../src/setup-cli.mjs';
const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../../..'), shipped = path.resolve(here, '../guidance');
const temp = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-guidance-')));
process.on('exit', () => fs.rmSync(temp, { recursive: true, force: true }));
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const docs = { memo: 'docs/test-authoring-memo.md', policy: 'docs/test-failure-policy.md' };
let sequence = 0;
function project() { const directory = path.join(temp, `project-${sequence++}`); fs.mkdirSync(directory); return directory; }
async function run(args) {
  const before = console.log, lines = [];
  console.log = (...parts) => lines.push(parts.join(' '));
  try { const status = await main(['guidance', ...args], { runtimeRoot: '/missing' }); return { status, report: JSON.parse(lines.join('\n')) }; } finally { console.log = before; }
}
const block = key => `<!-- e2e-skills:${GUIDANCE[key].name} sha256=${GUIDANCE[key].sha256} -->\n${guidanceText(key)}<!-- /e2e-skills:${GUIDANCE[key].name} -->\n`;
test('shipped texts are byte-identical to the documented blocks and their stated SHA-256', () => {
  for (const [key, doc] of Object.entries(docs)) {
    const source = fs.readFileSync(path.join(repo, doc), 'utf8');
    const blocks = [...source.matchAll(/^```text\n([\s\S]*?)^```$/gm)];
    assert.equal(blocks.length, 1, `${doc} has exactly one text block`);
    const bytes = fs.readFileSync(path.join(shipped, GUIDANCE[key].name + '.txt'));
    assert.equal(bytes.toString('utf8'), blocks[0][1], `${key} text matches ${doc}`);
    assert.match(source, new RegExp(`SHA-256 \`${GUIDANCE[key].sha256}\``), `${doc} states the pinned digest`);
    assert.equal(sha(bytes), GUIDANCE[key].sha256);
    assert.equal(guidanceText(key), blocks[0][1]);
  }
});
test('creates a missing file, appends after one blank line, then stays current', async () => {
  const dir = project(), target = path.join(dir, 'CLAUDE.md');
  let { status, report } = await run(['--host', 'claude', '--project', dir, '--memo']);
  assert.equal(status, 0); assert.equal(report.file, 'CREATED'); assert.equal(report.target, target);
  assert.deepEqual(report.blocks.map(entry => entry.status), ['CREATED']);
  assert.equal(fs.readFileSync(target, 'utf8'), block('memo'));
  const agents = path.join(dir, 'AGENTS.md'); fs.writeFileSync(agents, '# Project\nKeep this.'); fs.chmodSync(agents, 0o640);
  ({ report } = await run(['--host', 'codex', '--project', dir, '--policy']));
  assert.equal(report.file, 'UPDATED'); assert.deepEqual(report.blocks.map(entry => entry.status), ['ADDED']);
  assert.equal(fs.readFileSync(agents, 'utf8'), '# Project\nKeep this.\n\n' + block('policy'));
  assert.equal(fs.statSync(agents).mode & 0o777, 0o640, 'existing mode preserved');
  const stat = fs.statSync(agents);
  ({ report } = await run(['--host', 'codex', '--project', dir, '--policy']));
  assert.equal(report.file, 'CURRENT'); assert.deepEqual(report.blocks.map(entry => entry.status), ['CURRENT']);
  assert.equal(fs.statSync(agents).ino, stat.ino, 'current content is not rewritten');
  assert.deepEqual(fs.readdirSync(dir).sort(), ['AGENTS.md', 'CLAUDE.md'], 'no temporary files left');
});
test('replaces only a changed marked block and handles both flags', async () => {
  const dir = project(), target = path.join(dir, 'CLAUDE.md'), name = GUIDANCE.memo.name;
  const head = '# Rules\n\nBefore.\n', tail = '\nAfter the block.\n';
  fs.writeFileSync(target, `${head}<!-- e2e-skills:${name} sha256=${'0'.repeat(64)} -->\nold edited text\n<!-- /e2e-skills:${name} -->${tail}`);
  const { report } = await run(['--host', 'claude', '--project', dir, '--memo', '--policy']);
  assert.equal(report.file, 'UPDATED'); assert.deepEqual(report.blocks.map(entry => [entry.name, entry.status]), [[name, 'UPDATED'], [GUIDANCE.policy.name, 'ADDED']]);
  assert.equal(fs.readFileSync(target, 'utf8'), head + block('memo').slice(0, -1) + tail + '\n' + block('policy'));
  const again = await run(['--host', 'claude', '--project', dir, '--policy', '--memo']);
  assert.equal(again.report.file, 'CURRENT');
});
test('malformed markers, symlinks, special files and outside targets are refused without writes', async () => {
  const name = GUIDANCE.memo.name, start = `<!-- e2e-skills:${name} sha256=${GUIDANCE.memo.sha256} -->\n`, end = `<!-- /e2e-skills:${name} -->\n`;
  for (const content of [start + 'x\n', end, start + 'x\n' + end + start + 'y\n' + end, start + `<!-- e2e-skills:${GUIDANCE.policy.name} sha256=${GUIDANCE.policy.sha256} -->\n` + end, '  ' + start + end, `<!-- e2e-skills:${name} -->\n` + end, `<!-- e2e-skills:other sha256=${GUIDANCE.memo.sha256} -->\n<!-- /e2e-skills:other -->\n`]) {
    const dir = project(), target = path.join(dir, 'CLAUDE.md'); fs.writeFileSync(target, content);
    await assert.rejects(run(['--host', 'claude', '--project', dir, '--memo']), /marker|block/);
    assert.equal(fs.readFileSync(target, 'utf8'), content); assert.deepEqual(fs.readdirSync(dir), ['CLAUDE.md']);
  }
  const outside = path.join(temp, 'outside.md'); fs.writeFileSync(outside, 'outside\n');
  const linked = project(); fs.symlinkSync(outside, path.join(linked, 'AGENTS.md'));
  await assert.rejects(run(['--host', 'codex', '--project', linked, '--policy']), /symlink/);
  const hard = project(); fs.linkSync(outside, path.join(hard, 'AGENTS.md'));
  await assert.rejects(run(['--host', 'codex', '--project', hard, '--policy']), /outside the project|hard links/);
  assert.equal(fs.readFileSync(outside, 'utf8'), 'outside\n');
  const directory = project(); fs.mkdirSync(path.join(directory, 'CLAUDE.md'));
  await assert.rejects(run(['--host', 'claude', '--project', directory, '--memo']), /not a regular file/);
  const file = path.join(temp, 'not-a-directory'); fs.writeFileSync(file, '');
  await assert.rejects(run(['--host', 'claude', '--project', file, '--memo']), /not a directory/);
});
test('dry-run reports the text and writes nothing', async () => {
  const dir = project();
  const { report } = await run(['--host', 'claude', '--project', dir, '--memo', '--policy', '--dry-run']);
  assert.equal(report.dry_run, true); assert.equal(report.file, 'CREATED');
  assert.deepEqual(report.blocks.map(entry => entry.text), [block('memo'), block('policy')]);
  assert.deepEqual(fs.readdirSync(dir), []);
  fs.writeFileSync(path.join(dir, 'CLAUDE.md'), 'x\n');
  const updated = await run(['--host', 'claude', '--project', dir, '--memo', '--dry-run']);
  assert.equal(updated.report.file, 'UPDATED'); assert.equal(fs.readFileSync(path.join(dir, 'CLAUDE.md'), 'utf8'), 'x\n');
});
test('guidance is opt-in and parses fail-closed', async () => {
  const dir = project();
  for (const args of [
    ['--host', 'claude', '--project', dir],
    ['--host', 'claude', '--project', dir, '--dry-run'],
    ['--host', 'claude', '--memo'],
    ['--project', dir, '--memo'],
    ['--host', 'claude', '--project', dir, '--memo', '--memo'],
    ['--host', 'claude', '--project', dir, '--policy', '--policy'],
    ['--host', 'claude', '--project', dir, '--memo', '--check-server'],
    ['--host', 'claude', '--project', dir, '--project', dir, '--memo'],
  ]) await assert.rejects(main(['guidance', ...args], { runtimeRoot: '/missing' }), /requires|required|duplicate|unknown/);
  assert.deepEqual(fs.readdirSync(dir), []);
  for (const command of ['install', 'doctor']) await assert.rejects(main([command, '--host', 'claude', '--memo'], { runtimeRoot: '/missing' }), /unknown/);
});

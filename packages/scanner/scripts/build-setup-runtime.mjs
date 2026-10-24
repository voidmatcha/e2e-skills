#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Explicit, dependency-free release build. Never runs during package installation.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { verifyRuntime } from '../src/setup-cli.mjs';
const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
export function buildSetupRuntime(root = sourceRoot, output = path.join(root, 'packages/scanner/setup-runtime'), { check = false } = {}) {
const files = new Map(), modes = new Map();
for (let ancestor = path.resolve(output); ; ancestor = path.dirname(ancestor)) {
  try { if (fs.lstatSync(ancestor).isSymbolicLink()) throw Error(`refusing symlinked output path: ${ancestor}`); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (path.dirname(ancestor) === ancestor) break;
}
function collect(relative) {
  const name = path.posix.basename(relative);
  if (['__pycache__', 'node_modules', '.git', '.cache', '.pytest_cache', '.DS_Store', 'test-results', 'playwright-report', '.npmrc', 'auth.json'].includes(name) || /\.py[co]$|\.local\.md$/.test(name)) return;
  const source = path.join(root, relative), stat = fs.lstatSync(source);
  if (stat.isDirectory()) for (const name of fs.readdirSync(source).sort()) collect(relative + '/' + name);
  else if (stat.isFile()) { files.set(relative, fs.readFileSync(source)); modes.set(relative, stat.mode & 0o777); }
  else throw Error(`setup source is not a regular file/directory: ${relative}`);
}
for (const file of ['install.sh', 'LICENSE', 'NOTICE', ...['setup.mjs', 'reinstall-skills.sh', 'install-codex-agents.sh', 'install-claude-agents.sh', 'skills-cli-bootstrap-package.json', 'skills-cli-bootstrap-package-lock.json', 'skills-cli-installed-tree-sha256.json'].map(name => 'scripts/dev/' + name), 'scripts/dev/vendor/smol-toml', 'agents/e2e-finding-verifier.md', 'agents/e2e-failure-classifier.md', '.codex/agents/e2e-finding-verifier.toml', '.codex/agents/e2e-failure-classifier.toml', ...['cypress-debugger', 'e2e-reviewer', 'playwright-debugger', 'playwright-test-generator'].map(name => 'skills/' + name)]) collect(file);
const manifest = { version: 1, generator: 'e2e-skills-setup-runtime', files: Object.fromEntries([...files].sort(([a], [b]) => a.localeCompare(b, 'en')).map(([name, bytes]) => [name, { sha256: crypto.createHash('sha256').update(bytes).digest('hex'), size: bytes.length, mode: modes.get(name) }])) };
modes.set('inventory.json', 0o644);
files.set('inventory.json', Buffer.from(JSON.stringify(manifest, null, 2) + '\n'));
if (check) {
  const actual = [];
  function walk(folder, relative = '') {
    for (const name of fs.readdirSync(folder).sort()) {
      const rel = relative ? relative + '/' + name : name, target = path.join(folder, name), stat = fs.lstatSync(target);
      if (stat.isDirectory()) walk(target, rel);
      else if (stat.isFile()) actual.push(rel);
      else throw Error(`invalid setup payload entry: ${rel}`);
    }
  }
  verifyRuntime(output);
  walk(output);
  if (actual.length !== files.size || actual.some(name => !files.has(name) || (!fs.readFileSync(path.join(output, name)).equals(files.get(name)) || (fs.statSync(path.join(output, name)).mode & 0o777) !== modes.get(name)))) throw Error('setup-runtime is stale; rebuild it explicitly');
} else {
  if (fs.existsSync(output)) {
    verifyRuntime(output);
    if (JSON.parse(fs.readFileSync(path.join(output, 'inventory.json'), 'utf8')).generator !== 'e2e-skills-setup-runtime') throw Error('refusing unrelated output directory');
    fs.rmSync(output, { recursive: true });
  }
  for (const [name, bytes] of files) { const target = path.join(output, name); fs.mkdirSync(path.dirname(target), { recursive: true }); fs.writeFileSync(target, bytes, { mode: modes.get(name) }); fs.chmodSync(target, modes.get(name)); }
}
console.error(`setup-runtime: ${files.size} files, ${[...files.values()].reduce((sum, bytes) => sum + bytes.length, 0)} bytes${check ? ' verified' : ' built'}`);
return { files: files.size, bytes: [...files.values()].reduce((sum, bytes) => sum + bytes.length, 0) };
}
if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let output, check = false;
  const args = process.argv.slice(2);
  for (let index = 0; index < args.length; index++) {
    if (args[index] === '--check' && !check) check = true;
    else if (args[index] === '--output' && !output && args[index + 1] && path.isAbsolute(args[index + 1])) output = args[++index];
    else throw Error('Usage: node scripts/build-setup-runtime.mjs [--check] [--output /absolute/path]');
  }
  buildSetupRuntime(sourceRoot, output, { check });
}
